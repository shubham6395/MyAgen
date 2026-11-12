from __future__ import annotations

import logging

from myagent import approver, prompts, roles
from myagent import facts as facts_mod
from myagent.llm import ContextOverflowError, LLMError, NullLLM
from myagent.render.assemble import assemble_doc, parse_markers
from myagent.render.narrative import clean_llm_narrative
from myagent.types import Config, DocResult, Issue, Role

log = logging.getLogger("myagent.agents")


class Worker:
    """One worker agent instance owning exactly one document."""

    def __init__(self, role: Role, llm, cfg: Config):
        self.role = role
        self.llm = llm
        self.cfg = cfg

    def draft(self, facts: dict, shared_context: str, attempt: int = 0,
              previous: str | None = None, issues: list[Issue] | None = None
              ) -> tuple[str, dict[str, str], list[str], bool]:
        role = self.role
        fhash = facts_mod.facts_sha256(facts)
        context, sources = roles.build_context(role, facts, self.cfg.context_tokens)
        if self.cfg.offline or isinstance(self.llm, NullLLM):
            md = assemble_doc(role, facts, {}, "offline", fhash, sources)
            return md, {}, sources, False

        system = prompts.role_system_prompt(role)
        user = self._user_prompt(context, shared_context, attempt, previous, issues)
        try:
            text = self._complete(system, user, context, shared_context, attempt, previous, issues, facts)
        except LLMError as e:
            log.warning("%s: LLM failed (%s); offline fallback", role.filename, e)
            md = assemble_doc(role, facts, {}, "offline", fhash, sources)
            return md, {}, sources, True

        narratives = {k: clean_llm_narrative(v) for k, v in parse_markers(text).items()}
        required = [s.id for s in role.sections if s.kind == "narrative"]
        missing = [sid for sid in required if sid not in narratives]
        degraded = False
        if missing:
            reminder = (user + "\n\nYou missed these sections: " + ", ".join(missing) +
                        ". Return ALL sections again, complete, with markers.")
            try:
                text2 = self.llm.complete(system, reminder, max_tokens=self.cfg.max_output_tokens)
                narratives.update({k: clean_llm_narrative(v) for k, v in parse_markers(text2).items()})
            except LLMError:
                pass
            if any(sid not in narratives for sid in required):
                degraded = True
        md = assemble_doc(role, facts, narratives, "llm", fhash, sources)
        return md, narratives, sources, degraded

    def _user_prompt(self, context, shared_context, attempt, previous, issues) -> str:
        if attempt == 0:
            return prompts.draft_user_prompt(self.role, context, shared_context)
        return prompts.revision_prompt(self.role, context, shared_context,
                                       previous or "", issues or [])

    def _complete(self, system, user, context, shared_context, attempt, previous, issues, facts):
        try:
            return self.llm.complete(system, user, max_tokens=self.cfg.max_output_tokens)
        except ContextOverflowError:
            log.info("%s: context overflow, halving slice budget", self.role.filename)
            context, _ = roles.build_context(self.role, facts, self.cfg.context_tokens // 2)
            user = self._user_prompt(context, shared_context, attempt, previous, issues)
            return self.llm.complete(system, user, max_tokens=self.cfg.max_output_tokens)


def run_doc(role: Role, facts: dict, shared_context: str, llm, cfg: Config) -> DocResult:
    fhash = facts_mod.facts_sha256(facts)
    offline = cfg.offline or isinstance(llm, NullLLM)
    worker = Worker(role, llm, cfg)
    md, narratives, sources, degraded = worker.draft(facts, shared_context)
    if offline or (degraded and not narratives):
        verdict = approver.review(role, md, facts, "offline")
        return DocResult(role_id=role.id, filename=role.filename, markdown=md,
                         status="written", mode="offline", rounds_used=0,
                         verdict=verdict, sources=sources, degraded=degraded)

    verdict = approver.review(role, md, facts, "llm", llm, shared_context)
    rounds = 0
    while not verdict.approved and rounds < cfg.max_rounds:
        rounds += 1
        log.info("%s: revision %d/%d (%d issues)", role.filename, rounds,
                 cfg.max_rounds, len(verdict.issues))
        md, narratives, sources, deg = worker.draft(
            facts, shared_context, attempt=rounds, previous=md, issues=verdict.issues)
        degraded = degraded or deg
        if degraded and not narratives:
            verdict = approver.review(role, md, facts, "offline")
            return DocResult(role_id=role.id, filename=role.filename, markdown=md,
                             status="written", mode="offline", rounds_used=rounds,
                             verdict=verdict, sources=sources, degraded=True)
        verdict = approver.review(role, md, facts, "llm", llm, shared_context)
    if not verdict.approved:
        notes = "\n".join(
            f"- [{i.severity}] ({i.check}): {i.message}"
            for i in verdict.issues if i.severity in ("blocker", "major")
        ) or "unresolved review issues"
        md = assemble_doc(role, facts, narratives, "llm", fhash, sources, review_notes=notes)
    return DocResult(role_id=role.id, filename=role.filename, markdown=md,
                     status="written", mode="llm", rounds_used=rounds,
                     verdict=verdict, sources=sources, degraded=degraded)