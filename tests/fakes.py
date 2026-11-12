from __future__ import annotations

import json


class FakeLLM:
    name = "fake"

    def __init__(self, responder=None):
        self.calls: list[tuple[str, str, bool]] = []
        self.responder = responder or (lambda system, user, json_mode: "")

    def complete(self, system: str, user: str, *, max_tokens=None, json_mode=False) -> str:
        self.calls.append((system, user, json_mode))
        out = self.responder(system, user, json_mode)
        if isinstance(out, Exception):
            raise out
        return out


def markers_response(role, text: str = "Detailed narrative content grounded in facts. " * 12) -> str:
    return "\n".join(
        f"===SECTION: {s.id}===\n{text}"
        for s in role.sections if s.kind == "narrative"
    )


def verdict_json(approved: bool = True, issues=()) -> str:
    return json.dumps({
        "approved": approved,
        "scores": {"accuracy": 5, "completeness": 4, "consistency": 5,
                   "actionability": 4, "clarity": 5},
        "issues": list(issues),
        "summary": "reviewed",
    })