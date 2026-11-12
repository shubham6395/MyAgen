import pytest

from myagent import facts


def test_new_facts_has_all_keys_and_validates():
    f = facts.new_facts()
    assert f["schema_version"] == facts.SCHEMA_VERSION
    assert set(facts.FACTS_KEYS) <= set(f)
    facts.validate_facts(f)


def test_validate_rejects_missing_key():
    f = facts.new_facts()
    del f["routes"]
    with pytest.raises(facts.FactsError):
        facts.validate_facts(f)


def test_validate_rejects_wrong_type():
    f = facts.new_facts()
    f["routes"] = {}
    with pytest.raises(facts.FactsError):
        facts.validate_facts(f)


def test_canonical_json_is_key_order_independent():
    a = facts.canonical_json({"b": 1, "a": {"y": 2, "x": 3}})
    b = facts.canonical_json({"a": {"x": 3, "y": 2}, "b": 1})
    assert a == b


def test_key_hashes_isolate_changes():
    f = facts.new_facts()
    h1 = facts.key_hashes(f)
    f["routes"].append({"method": "get", "path": "/x"})
    h2 = facts.key_hashes(f)
    assert h1["routes"] != h2["routes"]
    assert h1["models"] == h2["models"]
    assert set(h1) == set(facts.FACTS_KEYS)


def test_generated_at_excluded_from_hashes():
    f = facts.new_facts()
    h1 = facts.facts_sha256(f)
    f["generated_at"] = "2099-01-01T00:00:00+00:00"
    assert facts.facts_sha256(f) == h1