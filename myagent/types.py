from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    target: Path
    out: Path | None = None
    provider: str = "auto"
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    offline: bool = False
    only: list[str] | None = None
    full: bool = False
    max_rounds: int = 2
    concurrency: int = 4
    dry_run: bool = False
    timeout: float = 120.0
    max_retries: int = 3
    context_tokens: int = 16000
    max_output_tokens: int = 8000
    temperature: float = 0.2
    verbose: bool = False
    quiet: bool = False
    config_file: Path | None = None


@dataclass(frozen=True)
class Section:
    id: str
    title: str
    kind: str  # "facts" | "narrative"
    renderer: str | None = None
    guidance: str = ""
    min_chars: int = 200
    optional: bool = False


@dataclass(frozen=True)
class Role:
    id: str
    filename: str
    title: str
    purpose: str
    depends_on: tuple[str, ...] = ()
    sections: tuple[Section, ...] = ()
    watches: tuple[str, ...] = ()
    globs: tuple[str, ...] = ()
    slice_spec: tuple[tuple[str, str | None], ...] = ()


@dataclass
class Issue:
    check: str
    severity: str  # "blocker" | "major" | "minor"
    section: str | None
    message: str
    suggestion: str = ""


@dataclass
class Verdict:
    approved: bool
    issues: list[Issue] = field(default_factory=list)
    scores: dict[str, int] | None = None
    summary: str = ""
    stage: str = "deterministic"  # deterministic | llm | both | deterministic-only


@dataclass
class DocTask:
    role: Role
    facts: dict
    shared_context: str = ""
    mode: str = "offline"
    attempt: int = 0
    previous_markdown: str | None = None
    issues: list[Issue] | None = None


@dataclass
class DocResult:
    role_id: str
    filename: str
    markdown: str = ""
    status: str = "written"  # written | skipped | failed
    mode: str = "offline"
    rounds_used: int = 0
    verdict: Verdict | None = None
    sources: list[str] = field(default_factory=list)
    degraded: bool = False
    error: str | None = None


@dataclass
class RunReport:
    started_at: str = ""
    finished_at: str = ""
    target: str = ""
    mode: str = "offline"
    facts_summary: dict = field(default_factory=dict)
    docs: list[DocResult] = field(default_factory=list)
    affected: list[str] = field(default_factory=list)
    up_to_date: list[str] = field(default_factory=list)
    exit_code: int = 0