import pytest

from myagent import facts, roles, util
from myagent.render import RENDERERS


def test_sixteen_roles_unique_files():
    assert len(roles.ROLES) == 16
    filenames = [r.filename for r in roles.ROLES]
    assert len(set(filenames)) == 16
    assert "BLUEPRINT.md" in filenames


def test_depends_acyclic_and_valid():
    ids = {r.id for r in roles.ROLES}
    for r in roles.ROLES:
        assert set(r.depends_on) <= ids
    resolved: set[str] = set()
    remaining = list(roles.ROLES)
    while remaining:
        ready = [r for r in remaining if set(r.depends_on) <= resolved]
        assert ready, "dependency cycle detected"
        for r in ready:
            resolved.add(r.id)
        remaining = [r for r in remaining if r.id not in resolved]


def test_renderers_and_watches_valid():
    for r in roles.ROLES:
        assert set(r.watches) <= set(facts.FACTS_KEYS)
        for s in r.sections:
            if s.kind == "facts":
                assert s.renderer in RENDERERS, f"{r.id}: unknown renderer {s.renderer}"
        assert any(s.kind == "narrative" for s in r.sections)


def test_get_role():
    assert roles.get_role("api").id == "API"
    assert roles.get_role("API.md").id == "API"
    with pytest.raises(KeyError):
        roles.get_role("NOPE")


def test_build_context_budget():
    f = facts.new_facts()
    f["symbols"] = [
        {"file": f"m{i}.py", "name": f"s{i}", "qualname": f"s{i}",
         "kind": "function", "lineno": i}
        for i in range(50000)
    ]
    role = roles.get_role("IMPLEMENTATION")
    ctx, sources = roles.build_context(role, f, budget_tokens=4000)
    assert util.estimate_tokens(ctx) <= 4000
    assert "truncated" in ctx


def test_build_context_sources():
    f = facts.new_facts()
    f["routes"] = [{"file": "main.py", "method": "GET", "path": "/x", "lineno": 1}]
    role = roles.get_role("API")
    ctx, sources = roles.build_context(role, f)
    assert "main.py" in sources
    assert "/x" in ctx


def test_blueprint_watches_all():
    bp = roles.get_role("BLUEPRINT")
    assert set(bp.watches) == set(facts.FACTS_KEYS)