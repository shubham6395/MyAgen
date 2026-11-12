from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path

from myagent import __version__, config, orchestrator, report, roles, updater
from myagent.analyzer import analyze_repo
from myagent.llm import make_client
from myagent.types import Config, RunReport

log = logging.getLogger("myagent")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="myagent",
        description="Multi-agent codebase documentation generator: 16-doc suite with approver review and incremental updates.",
    )
    p.add_argument("path", nargs="?", help="path to the codebase to document")
    p.add_argument("--out", metavar="DIR", help="output directory (default: <target>/docs)")
    p.add_argument("--provider", choices=sorted(config.VALID_PROVIDERS),
                   help="LLM provider (default: auto-detect from env)")
    p.add_argument("--model", help="model id (default: provider default)")
    p.add_argument("--base-url", help="override provider endpoint")
    p.add_argument("--config", metavar="FILE", help="explicit myagent.config.json")
    p.add_argument("--only", metavar="LIST", help="comma list of docs, e.g. PRD,API.md")
    p.add_argument("--full", action="store_true", help="regenerate all docs, ignore manifest")
    p.add_argument("--offline", action="store_true", help="deterministic mode, zero network")
    p.add_argument("--max-rounds", type=int, help="max approver revision rounds (default 2)")
    p.add_argument("--concurrency", type=int, help="worker agents in parallel (default 4)")
    p.add_argument("--dry-run", action="store_true", help="analyze and print plan; write nothing")
    p.add_argument("--timeout", type=float, help="per-HTTP-call timeout seconds (default 120)")
    p.add_argument("--max-retries", type=int, help="retries per LLM call (default 3)")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("-q", "--quiet", action="store_true")
    p.add_argument("--version", action="version", version=f"myagent {__version__}")
    return p


def _setup_logging(verbose: bool, quiet: bool) -> None:
    import sys
    level = logging.DEBUG if verbose else (logging.WARNING if quiet else logging.INFO)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)-7s %(message)s", "%H:%M:%S"))
    root = logging.getLogger("myagent")
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def _facts_summary(facts: dict) -> dict:
    return {
        "files": facts["repo"]["file_count"],
        "primary_language": facts["repo"]["primary_language"],
        "routes": len(facts["routes"]),
        "models": len(facts["models"]),
        "dependencies": len(facts["dependencies"]["runtime"]),
        "env_vars": len(facts["env_vars"]),
        "mcp_servers": sum(len(c["servers"]) for c in facts["mcp"]["configs"]),
    }


def run_pipeline(cfg: Config, llm=None) -> RunReport:
    started = datetime.now(timezone.utc).isoformat()
    target = Path(cfg.target).resolve()
    if not target.is_dir():
        raise NotADirectoryError(f"target is not a directory: {target}")
    out = Path(cfg.out).resolve() if cfg.out else target / "docs"
    facts = analyze_repo(target, out_dir=out)
    offline, reason = config.detect_offline(cfg)
    if offline and not cfg.offline:
        log.warning("Falling back to OFFLINE mode: %s", reason)
    mode = "offline" if offline else "llm"
    cfg.offline = offline
    if llm is None:
        llm = make_client(cfg)
    affected, up_to_date, manifest = updater.plan_run(target, out, facts, cfg, mode)
    if cfg.only:
        selected = {roles.get_role(n).id for n in cfg.only}
        affected = [a for a in affected if a in selected]
    rep = RunReport(started_at=started, target=str(target), mode=mode,
                    facts_summary=_facts_summary(facts),
                    affected=affected, up_to_date=up_to_date)
    log.info("Analyzed %d files (%s) | %d routes | %d models | %d deps",
             facts["repo"]["file_count"], facts["repo"]["primary_language"],
             len(facts["routes"]), len(facts["models"]),
             len(facts["dependencies"]["runtime"]))
    log.info("Plan: %d affected | %d up-to-date | mode: %s",
             len(affected), len(up_to_date), mode)
    if cfg.dry_run:
        rep.finished_at = datetime.now(timezone.utc).isoformat()
        rep.exit_code = 0
        return rep
    results = orchestrator.run(out, facts, cfg, llm, affected)
    out.mkdir(parents=True, exist_ok=True)
    for res in results:
        if res.status == "written":
            (out / res.filename).write_text(res.markdown, encoding="utf-8", newline="\n")
    updater.save_manifest(target, out, facts, cfg, mode, results, manifest)
    rep.docs = results
    rep.finished_at = datetime.now(timezone.utc).isoformat()
    rep.exit_code = report.compute_exit_code(rep)
    report.write_report(target, rep)
    return rep


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.verbose, args.quiet)
    if not args.path:
        parser.print_help()
        return 2
    target = Path(args.path)
    if not target.exists():
        log.error("path does not exist: %s", target)
        return 2
    overrides = {
        "out": args.out, "provider": args.provider, "model": args.model,
        "base_url": args.base_url, "config_file": args.config,
        "only": [x.strip() for x in args.only.split(",")] if args.only else None,
        "max_rounds": args.max_rounds, "concurrency": args.concurrency,
        "timeout": args.timeout, "max_retries": args.max_retries,
        "verbose": args.verbose or None, "quiet": args.quiet or None,
    }
    for flag in ("full", "offline", "dry_run"):
        if getattr(args, flag):
            overrides[flag] = True
    try:
        cfg = config.resolve_config(target, overrides)
    except ValueError as e:
        log.error("%s", e)
        return 2
    if cfg.only:
        try:
            for name in cfg.only:
                roles.get_role(name)
        except KeyError as e:
            log.error("%s", e)
            return 2
    try:
        rep = run_pipeline(cfg)
    except NotADirectoryError as e:
        log.error("%s", e)
        return 3
    except OSError as e:
        log.error("analysis/IO failure: %s", e)
        return 3
    except KeyboardInterrupt:
        return 130
    if cfg.dry_run:
        print("Dry run — no files written.")
        print(f"Mode: {rep.mode} | affected: {len(rep.affected)} | up-to-date: {len(rep.up_to_date)}")
        for rid in rep.affected:
            role = roles.get_role(rid)
            print(f"  {role.filename:<18} (watches: {', '.join(role.watches[:4])}...)")
        return 0
    for line in report.summarize(rep).splitlines():
        log.info("%s", line)
    log.info("Docs:   %s", (Path(cfg.out) if cfg.out else target / "docs"))
    log.info("Report: %s", target / ".myagent" / "report.json")
    return rep.exit_code