"""tools/refresh 파서·카탈로그 단위 테스트(네트워크·Qt 불필요, 작은 마크다운 조각 사용)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from refresh.catalog import (  # noqa: E402
    build_catalog,
    is_managed_only,
    parse_default,
    parse_scope,
    parse_topic,
    type_prose_schema,
    update_history,
)
from refresh.changelog import added_versions, latest_version  # noqa: E402
from refresh.codegen import info_args, top_order  # noqa: E402
from refresh.envvars import build_env_registry  # noqa: E402
from refresh.markdown import DocEntry, parse_settings_reference  # noqa: E402
from refresh.pkg import JsonType, Scope, Topic, Version  # noqa: E402

REFERENCE = """# All settings

## Settings index

| Key | Description | Topic | Scope |
| :- | :- | :- | :- |
| [`newKey`](#newkey) | Pick a thing | Model and responses | User or managed |
| [`oldKey`](#oldkey) | Deprecated; use `newKey` to pick | Model and responses | Any file |
| [`goneKey`](#gonekey) | Removed in v2.1.50, together with X | Memory and context | Any file |
| [`box.inner`](#box-inner) | Inner flag | Tools | Managed |

## Model and responses

### `newKey`

Pick a thing for every session. Requires Claude Code v2.1.100 or later.

* **Scope**: [`User or managed`](#scopes). Ignored elsewhere.
* **Type**: string, one of:
  * `"a"`: the first
  * `"b"`: the second
* **Default**: `"a"`

Later prose that Requires Claude Code v2.1.999 or later for a sub-feature.

### `goneKey`

Sizes the old tool. Once set, the prompt shows a notice:

> Old notice

### `oldKey`

> [!WARNING]
>
> Deprecated since v2.1.80, when [`newKey`](#newkey) replaced it.

Old way to pick.

* **Scope**: [`Any file`](#scopes)
* **Type**: Boolean
* **Default**: unset

### `box.inner`

Inner flag.

* **Scope**: [`Managed`](#scopes)
* **Type**: number of seconds, from `1` to `60`
* **Default**: `5`
"""


def _entry(type_text, bullets=()):
    return DocEntry("k", type_text=type_text, type_bullets=list(bullets))


def test_parse_settings_reference_index_and_sections():
    e = parse_settings_reference(REFERENCE)
    assert list(e) == ["newKey", "oldKey", "goneKey", "box.inner"]
    n = e["newKey"]
    assert (n.scope_text, n.topic, n.since, n.default_text) == ("User or managed", "Model and responses", "2.1.100", '`"a"`')
    assert n.description.startswith("Pick a thing") and n.type_bullets == ['`"a"`: the first', '`"b"`: the second']
    o = e["oldKey"]
    assert o.deprecated and o.deprecated_since == "2.1.80" and o.replaced_by == "newKey"
    assert e["goneKey"].removed == "2.1.50"
    assert e["goneKey"].description == "Sizes the old tool."                  # ':' 로 끝나는 안내 문장은 뗀다
    assert e["box.inner"].scope_text == "Managed"


def test_scope_words_map_to_flags():
    assert parse_scope("Any file") == Scope.ANY_FILE
    assert parse_scope("User or managed") == Scope.USER | Scope.MANAGED
    assert parse_scope("User, local, or managed") == Scope.USER | Scope.LOCAL | Scope.MANAGED
    assert parse_scope("Global config") == Scope.GLOBAL_CONFIG
    with pytest.raises(ValueError):
        parse_scope("Everywhere")
    assert parse_topic("Model and responses") is Topic.MODEL and parse_topic("") is None
    with pytest.raises(ValueError, match="constants.Topic"):
        parse_topic("Brand new topic")


def test_type_prose_to_schema():
    assert type_prose_schema(_entry("Boolean")) == {"type": "boolean"}
    assert type_prose_schema(_entry('string, one of `"low"`, `"high"`, or `"max"`. A `"max"` value sets more')) == \
        {"type": "string", "enum": ["low", "high", "max"]}
    assert type_prose_schema(_entry("string, one of:", ['`"auto"`: x', '`"24-hour"`: y', 'A strftime pattern'])) == \
        {"anyOf": [{"type": "string", "enum": ["auto", "24-hour"]}, {"type": "string"}]}
    assert type_prose_schema(_entry("string, an IANA time zone name")) == {"type": "string"}
    assert type_prose_schema(_entry("number of tokens, from `100000` to `1000000`")) == \
        {"type": "integer", "minimum": 100000, "maximum": 1000000}
    assert type_prose_schema(_entry("number of characters, a positive integer")) == {"type": "integer", "minimum": 1}
    assert type_prose_schema(_entry("array of strings, each one of:", ['`"bedrock"`: x', '`"vertex"`: y'])) == \
        {"type": "array", "items": {"type": "string", "enum": ["bedrock", "vertex"]}}
    assert type_prose_schema(_entry("array of `plugin-name@marketplace-name` strings")) == \
        {"type": "array", "items": {"type": "string"}}
    assert type_prose_schema(_entry("object with an `options` array")) is None   # overrides 로 보완
    assert parse_default('`"prefix"`') == "prefix" and parse_default("`false`") is False
    assert parse_default("unset, so nothing") is None


def test_managed_only_description_patterns():
    assert is_managed_only({"description": "(Managed settings only) Org rules"})
    assert is_managed_only({"description": "(Windows managed settings only) x"})
    assert is_managed_only({"description": "Only honored from managed (policy) settings."})
    assert not is_managed_only({"description": "Deploy it in managed settings to enforce it."})


def test_changelog_versions():
    md = "# Changelog\n\n## 2.1.300\n\n- Added `newKey` setting to pick\n- Fixed `oldKey` crash\n\n" \
         "## 2.1.10\n\n- [VSCode] Added the `oldKey` and `box.inner` settings\n- Added support for X in `newKey`\n"
    assert latest_version(md) == "2.1.300"
    assert added_versions(md, {"newKey", "oldKey", "box.inner"}) == {"oldKey": "2.1.10", "box.inner": "2.1.10",
                                                                     "newKey": "2.1.300"}


def test_history_detects_new_and_removed_keys():
    h = update_history({}, ["a", "b"], "2.1.10")
    assert h["seededAt"] == "2.1.10" and h["paths"]["a"] == {"firstSeen": "2.1.10", "lastSeen": "2.1.10"}
    h = update_history(h, ["a", "c"], "2.1.20")
    assert h["paths"]["b"]["removedBy"] == "2.1.20" and h["paths"]["c"]["firstSeen"] == "2.1.20"
    h = update_history(h, ["a", "b", "c"], "2.1.30")
    assert "removedBy" not in h["paths"]["b"]                                     # 다시 나타나면 해제


def _catalog():
    store = {"properties": {"oldKey": {"type": "boolean", "description": "old"},
                            "box": {"type": "object", "properties": {}}}}
    docs = parse_settings_reference(REFERENCE)
    history = update_history(update_history({}, ["oldKey"], "2.1.1"), list(docs), "2.1.200")
    return build_catalog(store, docs, {"oldKey": "2.1.5"}, history, {"oldKey": {"since": "2.0.1"}})


def test_build_catalog_injects_docs_only_keys_and_merges_metadata():
    docs = parse_settings_reference(REFERENCE)
    schema, top, nested, notes = _catalog()
    assert schema["properties"]["newKey"] == {"type": "string", "enum": ["a", "b"], "description": docs["newKey"].description,
                                              "default": "a"}
    assert schema["properties"]["box"]["properties"]["inner"]["maximum"] == 60
    assert top["newKey"]["scope"] == Scope.USER | Scope.MANAGED and top["newKey"]["since"] == Version(2, 1, 100)
    assert top["newKey"]["type"] == JsonType.STRING and top["newKey"]["topic"] is Topic.MODEL
    assert top["newKey"]["in_docs"] and not top["newKey"]["in_schemastore"]
    assert top["oldKey"]["since"] == Version(2, 0, 1)                             # overrides > CHANGELOG
    assert top["oldKey"]["replaced_by"] == "newKey" and top["goneKey"]["removed"] == Version(2, 1, 50)
    assert nested["box.inner"]["scope"] == Scope.MANAGED and nested["box.inner"]["default"] == 5
    assert any("goneKey" in n for n in notes)                                     # Type 이 없어 raw JSON


def test_codegen_writes_constant_references_not_strings():
    _, top, nested, _ = _catalog()
    order = top_order(top)
    assert list(top).index("oldKey") < list(top).index("newKey")              # 스키마 순서로는 대체 키가 뒤
    assert order.index("newKey") < order.index("oldKey")                      # 클래스 본문에서 이름으로 참조하도록 앞당김
    args = info_args("oldKey", top["oldKey"], "newKey")
    assert {"type=JsonType.BOOLEAN", "since=Version(2, 0, 1)", "deprecated_since=Version(2, 1, 80)",
            "replaced_by=newKey", "topic=Topic.MODEL"} <= set(args)
    assert info_args("box.inner", nested["box.inner"])[:3] == ['"box.inner"', "scope=Scope.MANAGED", "type=JsonType.INTEGER"]
    assert "scope=Scope.USER | Scope.MANAGED" in info_args("newKey", top["newKey"])


def test_env_registry_overrides_add_unlisted_variables():
    reg = build_env_registry({"properties": {"env": {"properties": {"A_VAR_NAME": {"description": "d"}}}}},
                             {"DOC_ONLY_VAR": "Set to 1 to enable"},
                             {"HAND_ADDED_VAR": {"description": "x", "values": ["0", "1"]}})
    assert reg["HAND_ADDED_VAR"] == {"description": "x", "schemaDescription": "", "values": ["0", "1"],
                                     "inSchema": False, "inDocs": False, "valuesAreHints": False}
    assert reg["DOC_ONLY_VAR"]["values"] == ["1", "0"] and reg["DOC_ONLY_VAR"]["valuesAreHints"]
