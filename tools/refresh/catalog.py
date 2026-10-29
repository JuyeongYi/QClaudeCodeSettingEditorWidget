"""카탈로그 생성: 문서(settings-reference) + schemastore 스키마 + CHANGELOG + 이력 + overrides → 병합 스키마와 키별 SettingInfo.

- 스코프: 문서 Scope 열이 기준. 문서에 없는 키는 스키마 설명의 관리형 전용 문구로 판별.
- 버전: since = overrides > 문서 "Requires Claude Code vX" > CHANGELOG "Added `key` setting" > 이력 firstSeen(시드 이후).
  removed / deprecated = overrides > 문서 경고 박스·색인 > 이력(문서에서 사라진 키).
- 스키마: schemastore 에 없는 문서 키를 **Type** 문장에서 만든 스키마(또는 overrides 의 schema)로 주입한다.
  Global config(~/.claude.json) 전용 키는 settings.json 이 아니므로 주입하지 않는다.
"""
from __future__ import annotations

import copy
import json
import re
from typing import Any

from .markdown import DocEntry, clean_markdown
from .pkg import JsonType, Scope, Topic, Version
from .pkg import schema as _S

# --------------------------------------------------------------------------- 스코프
_SCOPE_WORDS = {"any file": Scope.ANY_FILE, "user": Scope.USER, "project": Scope.PROJECT, "local": Scope.LOCAL,
                "managed": Scope.MANAGED, "global config": Scope.GLOBAL_CONFIG}
_MANAGED_ONLY = re.compile(
    r"^\([^)]*\bmanaged settings?\b[^)]*\)"          # "(Managed settings only)", "(Admin/managed settings only)" ...
    r"|only honored from managed \(policy\) settings"
    r"|honored only at the managed policy tier",
    re.I,
)


def parse_scope(text: str) -> Scope:
    """"User, local, or managed" → USER | LOCAL | MANAGED. 모르는 단어는 ValueError."""
    scope = Scope.NONE
    for word in re.split(r",\s*(?:or\s+)?|\s+or\s+", text.strip().lower()):
        if word:
            if word not in _SCOPE_WORDS:
                raise ValueError(f"unknown scope word {word!r} in {text!r}")
            scope |= _SCOPE_WORDS[word]
    return scope or Scope.ANY_FILE


def parse_topic(text: str) -> Topic | None:
    """색인표 Topic 열 → Topic. 비었으면 None, constants.Topic 에 없는 새 주제면 ValueError."""
    if not text:
        return None
    try:
        return Topic(text)
    except ValueError:
        raise ValueError(f"new docs topic {text!r}: add it to constants.Topic") from None


def _version(text: str | None) -> Version | None:
    return Version.parse(text) if text else None


def is_managed_only(node: dict) -> bool:
    """스키마 description 이 관리형(정책) 설정에서만 유효하다고 밝힌 노드인지(문서에 없는 키의 스코프 판별용)."""
    return bool(_MANAGED_ONLY.search((node.get("description") or "").strip()))


# --------------------------------------------------------------------------- Type 문장 → 스키마
_QUOTED = re.compile(r'`"([^"`]+)"`')


def _enum_from_bullets(bullets: list[str]) -> tuple[list[str], bool]:
    """'`"x"`: 설명' 불릿들 → (값들, 열린 집합 여부). 따옴표 리터럴로 시작하지 않는 불릿이 있으면 열린 집합."""
    values, open_set = [], False
    for b in bullets:
        m = re.match(r'`"([^"`]+)"`', b)
        if m:
            values.append(m.group(1))
        else:
            open_set = True
    return values, open_set


def _string_schema(values: list[str], open_set: bool) -> dict:
    if not values:
        return {"type": "string"}
    if open_set:
        return {"anyOf": [{"type": "string", "enum": values}, {"type": "string"}]}
    return {"type": "string", "enum": values}


def _number_schema(text: str) -> dict:
    integer = bool(re.search(r"whole number|integer|number of (?:tokens|characters|days|columns|seconds|minutes|"
                             r"milliseconds|lines|bytes|entries)", text))
    node: dict[str, Any] = {"type": "integer" if integer else "number"}
    num = r"`?(\d[\d_,]*(?:\.\d+)?)`?"

    def val(s: str):
        s = s.replace(",", "").replace("_", "")
        return int(s) if integer and "." not in s else float(s)

    if m := re.search(rf"from {num} to {num}", text):
        node["minimum"], node["maximum"] = val(m.group(1)), val(m.group(2))
    if m := re.search(rf"minimum {num}", text):
        node["minimum"] = val(m.group(1))
    if m := re.search(rf"at most {num}", text):
        node["maximum"] = val(m.group(1))
    if "positive integer" in text:
        node.setdefault("minimum", 1)
    return node


def type_prose_schema(entry: DocEntry) -> dict | None:
    """**Type** 문장에서 스키마를 추론. 객체·객체 배열처럼 구조를 알 수 없으면 None(overrides 로 보완)."""
    text, bullets = entry.type_text, entry.type_bullets
    low = text.lower()
    if low.startswith("boolean"):
        return {"type": "boolean"}
    if low.startswith("string"):
        if "one of:" in low:
            return _string_schema(*_enum_from_bullets(bullets))
        first = re.split(r"(?<=[.;])\s+(?=[A-Z`])", text, maxsplit=1)[0]  # 뒤따르는 부연 설명은 제외
        values = list(dict.fromkeys(_QUOTED.findall(first)))
        open_set = bool(re.search(r"such as|or a full|or any|or another", first.lower()))
        return _string_schema(values if len(values) >= 2 else [], open_set)
    if low.startswith("number"):
        return _number_schema(low)
    if low.startswith("array of"):
        if "each one of:" in low:
            values, _ = _enum_from_bullets(bullets)
            return {"type": "array", "items": {"type": "string", "enum": values}}
        if re.match(r"array of (?:[^,]*\b)?(?:strings|model aliases|ids|paths|names|globs|patterns)", low) \
                or re.match(r"array of `[^`]+` strings", low):
            return {"type": "array", "items": {"type": "string"}}
        return None
    return None


def parse_default(text: str) -> Any:
    """**Default** 문장이 JSON 리터럴(`true`, `"prefix"`, `5`)로 시작하면 그 값, 아니면 None."""
    m = re.match(r"`([^`]+)`", text.strip())
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError:
        return None


# --------------------------------------------------------------------------- 스키마 탐색·주입
def _deref(node: Any, root: dict) -> Any:
    """$ref 를 따라간 **실제** 대상 dict(복사 아님 — 주입용)."""
    seen = set()
    while isinstance(node, dict) and isinstance(node.get("$ref"), str) and node["$ref"] not in seen:
        seen.add(node["$ref"])
        target: Any = root
        for part in node["$ref"][2:].split("/"):
            target = target.get(part.replace("~1", "/").replace("~0", "~"), {}) if isinstance(target, dict) else {}
        node = target
    return node


def _object_at(root: dict, path: str) -> dict | None:
    """'sandbox.credentials' 경로의 객체 스키마(properties 를 가진 실제 dict)."""
    node: Any = root
    for part in path.split("."):
        props = _deref(node, root).get("properties", {}) if isinstance(_deref(node, root), dict) else {}
        if part not in props:
            return None
        node = props[part]
    node = _deref(node, root)
    return node if isinstance(node, dict) and isinstance(node.get("properties"), dict) else None


def schema_paths(root: dict) -> dict[str, dict]:
    """편집기가 쓰는 경로 표기(객체 'a.b', dict 값 'a.*', 배열 원소 'a[]')로 모든 노드를 나열(해석된 사본)."""
    out: dict[str, dict] = {}

    def walk(node: Any, path: str, depth: int) -> None:
        node = _S.resolve_ref(node, root)
        if not isinstance(node, dict) or depth > 12:
            return
        if path:
            out.setdefault(path, node)
        for variant in node.get("anyOf", []) + node.get("oneOf", []):
            walk(variant, path, depth + 1)
        for k, child in node.get("properties", {}).items():
            walk(child, f"{path}.{k}" if path else k, depth + 1)
        if isinstance(node.get("additionalProperties"), dict):
            walk(node["additionalProperties"], f"{path}.*", depth + 1)
        if isinstance(node.get("items"), dict):
            walk(node["items"], f"{path}[]", depth + 1)

    walk(root, "", 0)
    return out


def describe_type(node: dict, root: dict) -> tuple[JsonType, tuple, Any]:
    """해석된 스키마 노드 → (JSON 타입 플래그, 값 후보, 기본값)."""
    types = _S.schema_types(node)
    variants = _S.variants_of(node, root) if ("anyOf" in node or "oneOf" in node) else []
    if not types:
        for v in variants:
            types += [t for t in _S.schema_types(v) if t not in types]
    values: list = list(node.get("enum", []))
    for v in variants:
        values += [e for e in v.get("enum", []) if e not in values]
    items = _S.resolve_ref(node.get("items"), root) if isinstance(node.get("items"), dict) else {}
    values += [e for e in items.get("enum", []) if e not in values]
    return JsonType.parse("|".join(types)), tuple(values), node.get("default")


# --------------------------------------------------------------------------- 이력
def update_history(history: dict, doc_paths: list[str], version: str) -> dict:
    """문서에 보인 경로의 firstSeen/lastSeen 을 기록. 처음이면 seededAt 으로 시작한다."""
    history = copy.deepcopy(history) if history else {"seededAt": version, "paths": {}}
    paths = history.setdefault("paths", {})
    for p in doc_paths:
        rec = paths.setdefault(p, {"firstSeen": version})
        rec["lastSeen"] = version
        rec.pop("removedBy", None)
    for p, rec in paths.items():
        if p not in doc_paths and Version.parse(rec.get("lastSeen", version)) < Version.parse(version):
            rec.setdefault("removedBy", version)  # 문서에서 사라진 시점(이 갱신)을 상한으로 기록
    return history


def _history_since(history: dict, path: str) -> str | None:
    rec = history.get("paths", {}).get(path)
    seeded = history.get("seededAt")
    if rec and seeded and Version.parse(rec["firstSeen"]) > Version.parse(seeded):
        return rec["firstSeen"]
    return None


# --------------------------------------------------------------------------- 빌드
INFO_FIELDS = ("scope", "type", "default", "values", "since", "deprecated", "deprecated_since", "replaced_by",
               "removed", "topic", "in_docs", "in_schemastore")


def _make_info(path: str, entry: DocEntry | None, node: dict | None, root: dict, store_paths: set[str],
               added: dict[str, str], history: dict, override: dict) -> dict:
    if entry is not None:
        scope = parse_scope(entry.scope_text)
    else:
        scope = Scope.MANAGED if node is not None and is_managed_only(node) else Scope.ANY_FILE
    type_, values, default = describe_type(node, root) if node is not None else (JsonType.NONE, (), None)
    doc_default = parse_default(entry.default_text) if entry is not None else None
    rec = history.get("paths", {}).get(path, {})
    info = {
        "scope": scope,
        "type": type_,
        "default": doc_default if doc_default is not None else default,
        "values": values,
        "since": _version((entry.since if entry else None) or added.get(path) or _history_since(history, path)),
        "deprecated": bool(entry and entry.deprecated),
        "deprecated_since": _version(entry.deprecated_since if entry else None),
        "replaced_by": entry.replaced_by if entry else None,   # 경로 — codegen 이 대상 SettingInfo 참조로 바꾼다
        "removed": _version((entry.removed if entry else None) or rec.get("removedBy")),
        "topic": parse_topic(entry.topic if entry else ""),
        "in_docs": entry is not None,
        "in_schemastore": path in store_paths,
    }
    for k, v in override.items():
        if k == "scope":
            info[k] = Scope.parse(v)
        elif k == "type":
            info[k] = JsonType.parse(v)
        elif k == "topic":
            info[k] = parse_topic(v)
        elif k in ("since", "deprecated_since", "removed"):
            info[k] = _version(v)
        elif k in INFO_FIELDS:
            info[k] = tuple(v) if k == "values" else v
    return info


def build_catalog(store: dict, docs: dict[str, DocEntry], added: dict[str, str], history: dict,
                  overrides: dict[str, dict]) -> tuple[dict, dict[str, dict], dict[str, dict], list[str]]:
    """(병합 스키마, 최상위 키 info, 중첩 경로 info, 보고 줄)."""
    schema = copy.deepcopy(store)
    props: dict = schema.setdefault("properties", {})
    store_paths = set(schema_paths(store)) | set(store.get("properties", {}))
    notes: list[str] = []

    def node_for(path: str, entry: DocEntry) -> dict | None:
        ov = overrides.get(path, {})
        node = copy.deepcopy(ov["schema"]) if "schema" in ov else type_prose_schema(entry)
        if node is not None:
            node.setdefault("description", entry.description)
            if "default" not in node and (d := parse_default(entry.default_text)) is not None:
                node["default"] = d
        return node

    # 1) 문서에만 있는 키·중첩 경로를 스키마에 주입
    for path, entry in docs.items():
        if path in store_paths or parse_scope(entry.scope_text) == Scope.GLOBAL_CONFIG:
            continue
        if entry.type_text.lower().startswith("the string"):
            continue  # 배열 값 하나를 키처럼 적은 항목(strictPluginOnlyCustomization.agents 등) — 메타데이터만

        parent_path, _, leaf = path.rpartition(".")
        if parent_path and "." not in parent_path and parent_path not in props and parent_path not in docs:
            props[parent_path] = {"type": "object", "properties": {}}  # 문서가 중첩 키만 적은 객체(remote 등)
            notes.append(f"created parent object {parent_path} for {path}")
        parent = schema if not parent_path else _object_at(schema, parent_path)
        if parent is None:
            notes.append(f"skip nested {path}: parent is not a plain object")
            continue
        node = node_for(path, entry)
        if node is None:
            notes.append(f"raw JSON {path}: cannot infer schema from Type '{clean_markdown(entry.type_text)[:60]}'")
            node = {"description": entry.description}
        parent.setdefault("properties", {})[leaf] = node
    # overrides 의 schema 는 schemastore 에 있는 키도 교체한다
    for path, ov in overrides.items():
        if "schema" in ov and path in store_paths:
            parent_path, _, leaf = path.rpartition(".")
            parent = schema if not parent_path else _object_at(schema, parent_path)
            if parent is not None:
                parent["properties"][leaf] = copy.deepcopy(ov["schema"])

    # 2) 키별 info
    resolved = schema_paths(schema)
    top = {key: _make_info(key, docs.get(key), _S.resolve_ref(props[key], schema), schema, store_paths, added,
                           history, overrides.get(key, {}))
           for key in props}
    nested_paths = [p for p in docs if "." in p]
    nested_paths += [p for p, n in resolved.items() if "." in p and p not in docs and is_managed_only(n)]
    nested_paths += [p for p in overrides if "." in p and p not in nested_paths]
    nested = {p: _make_info(p, docs.get(p), resolved.get(p), schema, store_paths, added, history, overrides.get(p, {}))
              for p in nested_paths}
    for path in overrides:
        if path not in top and path not in nested:
            notes.append(f"override for unknown path {path}")
    return schema, top, nested, notes
