"""스키마 헬퍼·카테고리 단위 테스트(Qt 불필요)."""
from qclaudecodesettingeditorwidget import categories as C
from qclaudecodesettingeditorwidget import schema as S
from qclaudecodesettingeditorwidget.constants import ENV_KEY


def test_schema_loads_and_has_env():
    s = S.load_schema()
    assert "env" in s["properties"]
    assert len(s["properties"]) > 100


def test_every_top_level_key_is_categorized_once():
    s = S.load_schema()
    keys = list(s["properties"])
    cats = C.categorize(keys)
    seen = [k for _, ks in cats for k in ks]
    assert sorted(seen) == sorted(k for k in keys if k != ENV_KEY)
    assert len(seen) == len(set(seen))


def test_env_registry_covers_schema_and_docs():
    s = S.load_schema()
    reg = S.load_env_registry(schema=s)
    for name in s["properties"]["env"]["properties"]:
        assert name in reg and reg[name].in_schema
    assert reg["CLAUDE_CODE_EFFORT_LEVEL"].values == ["low", "medium", "high", "xhigh", "max", "auto"]
    assert any(v.in_docs and not v.in_schema for v in reg.values())  # 문서 전용 변수도 포함


def test_resolve_ref_merges_siblings():
    s = S.load_schema()
    node = {"$ref": "#/$defs/hookMatcher", "description": "override"}
    r = S.resolve_ref(node, s)
    assert r["type"] == "object" and r["description"] == "override"


def test_value_matches_variants():
    s = S.load_schema()
    p = s["properties"]
    assert S.value_matches(p["theme"], "custom:foo", s)
    assert not S.value_matches(p["theme"], "bogus", s)
    assert S.value_matches(p["enabledPlugins"], {"a@b": True, "c@d": ["x"]}, s)
    assert S.value_matches(p["strictPluginOnlyCustomization"], ["skills", "hooks"], s)
    assert not S.value_matches(p["strictPluginOnlyCustomization"], ["nope"], s)
    variants = S.variants_of(p["allowedMcpServers"]["items"], s)
    assert [S.variant_label(v) for v in variants] == ["serverName", "serverCommand", "serverUrl"]
    assert S.value_matches(variants[1], {"serverCommand": ["npx", "x"]}, s)
    assert not S.value_matches(variants[0], {"serverCommand": ["npx", "x"]}, s)


def test_first_sentence():
    assert S.first_sentence("Hello world. Second sentence here.") == "Hello world."
    assert S.first_sentence("No period at all") == "No period at all"
