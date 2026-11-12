from __future__ import annotations

from myagent.types import Role, Section

SENTINEL = "<!-- MYAGENT:NARRATIVE -->"


def _evidence_bullets(facts: dict, role: Role) -> list[str]:
    bullets = []
    for key, _filter in role.slice_spec:
        value = facts.get(key)
        if isinstance(value, list):
            if not value:
                bullets.append(f"- {key}: none detected")
                continue
            names = []
            for item in value[:3]:
                if isinstance(item, dict):
                    label = item.get("name") or item.get("path") or item.get("service") or item.get("file")
                    if item.get("method") and item.get("path"):
                        label = f"{item['method']} {item['path']}"
                    if label:
                        names.append(str(label))
            sample = f" (e.g. {', '.join(names)})" if names else ""
            bullets.append(f"- {key}: {len(value)} records{sample}")
        elif isinstance(value, dict):
            sub = ", ".join(f"{k}: {len(v) if isinstance(v, (list, dict)) else v}"
                            for k, v in list(value.items())[:5] if k != "root")
            bullets.append(f"- {key}: {sub}")
    return bullets[:8]


def offline_narrative(section: Section, facts: dict, role: Role) -> str:
    bullets = _evidence_bullets(facts, role)
    return (
        f"{SENTINEL}\n"
        f"> **Offline mode placeholder.** Configure an LLM provider "
        f"(MYAGENT_PROVIDER / MYAGENT_API_KEY) and re-run to generate this section.\n\n"
        f"**What belongs here:** {section.guidance}\n\n"
        f"**Evidence available:**\n" + "\n".join(bullets)
    )


def clean_llm_narrative(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text