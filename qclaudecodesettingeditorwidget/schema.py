"""스키마 로딩·$ref 해석·값 매칭 휴리스틱·env 레지스트리.

번들된 resources/claude-code-settings.schema.json 과 resources/env-vars.json 을 기본으로 쓰고,
load_schema(path) / load_env_registry(path) 로 외부 파일을 대신 쓸 수 있다.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

SCHEMA_RESOURCE = "claude-code-settings.schema.json"
ENV_RESOURCE = "env-vars.json"
OVERLAPS_RESOURCE = "overlaps.json"

JsonSchema = dict[str, Any]


# --------------------------------------------------------------------------- 로딩
def _read_resource(name: str) -> str:
    return resources.files(__package__).joinpath("resources", name).read_text("utf-8")


def load_schema(path: str | Path | None = None) -> JsonSchema:
    """설정 JSON 스키마 로드. path가 None이면 번들 리소스."""
    text = Path(path).read_text("utf-8") if path else _read_resource(SCHEMA_RESOURCE)
    return json.loads(text)


@dataclass
class EnvVarInfo:
    name: str
    description: str = ""
    values: list[str] = field(default_factory=list)
    values_are_hints: bool = False
    in_schema: bool = False
    in_docs: bool = False


def load_env_registry(path: str | Path | None = None, schema: JsonSchema | None = None) -> dict[str, EnvVarInfo]:
    """env 변수 레지스트리(문서+스키마 병합) 로드. 스키마에만 있는 변수도 항상 포함한다."""
    text = Path(path).read_text("utf-8") if path else _read_resource(ENV_RESOURCE)
    raw: dict[str, dict] = json.loads(text)
    out: dict[str, EnvVarInfo] = {}
    for name, e in raw.items():
        out[name] = EnvVarInfo(
            name=name,
            description=e.get("description", ""),
            values=list(e.get("values", [])),
            values_are_hints=bool(e.get("valuesAreHints", False)),
            in_schema=bool(e.get("inSchema", False)),
            in_docs=bool(e.get("inDocs", False)),
        )
    if schema is not None:  # 스키마가 레지스트리보다 새로울 때를 대비해 병합
        for name, prop in schema.get("properties", {}).get("env", {}).get("properties", {}).items():
            info = out.setdefault(name, EnvVarInfo(name=name))
            info.in_schema = True
            if not info.description:
                info.description = prop.get("description", "")
            if prop.get("enum") and (not info.values or info.values_are_hints):
                info.values = list(prop["enum"])
                info.values_are_hints = False
    return dict(sorted(out.items()))


def load_overlaps(path: str | Path | None = None) -> dict[str, list[dict[str, str]]]:
    """설정 키 ↔ env 변수 겹침 표: {settingKey: [{"env", "precedence": env|setting|related, "note"}]}.

    번들 리소스가 없으면 빈 dict. tools/refresh_resources.py 가 문서에서 추출해 만든다.
    """
    try:
        text = Path(path).read_text("utf-8") if path else _read_resource(OVERLAPS_RESOURCE)
    except (OSError, FileNotFoundError):
        return {}
    data = json.loads(text)
    return data if isinstance(data, dict) else {}


def overlaps_by_env(overlaps: dict[str, list[dict[str, str]]]) -> dict[str, list[tuple[str, str]]]:
    """env 변수 이름 → [(settingKey, precedence)] 역방향 표."""
    out: dict[str, list[tuple[str, str]]] = {}
    for key, entries in overlaps.items():
        for e in entries:
            out.setdefault(e["env"], []).append((key, e.get("precedence", "related")))
    return out


# --------------------------------------------------------------------------- $ref
def resolve_ref(node: Any, root: JsonSchema) -> JsonSchema:
    """$ref를 재귀적으로 해석. 순환 시 마지막 노드 반환. dict가 아니면 {}."""
    if not isinstance(node, dict):
        return {}
    seen: set[str] = set()
    current = node
    while "$ref" in current:
        ref = current["$ref"]
        if not isinstance(ref, str) or ref in seen or not ref.startswith("#/"):
            break
        seen.add(ref)
        target: Any = root
        for part in ref[2:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            if isinstance(target, dict) and part in target:
                target = target[part]
            else:
                return current
        if not isinstance(target, dict):
            break
        # $ref 옆의 형제 키(description 등)는 참조 대상 위에 덮어쓴다
        merged = dict(target)
        merged.update({k: v for k, v in current.items() if k != "$ref"})
        current = merged
    return current


# --------------------------------------------------------------------------- 유틸
def json_type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def schema_types(schema: JsonSchema) -> list[str]:
    t = schema.get("type")
    if isinstance(t, str):
        return [t]
    if isinstance(t, list):
        return [x for x in t if isinstance(x, str)]
    if "const" in schema:
        return [json_type_name(schema["const"])]
    if "enum" in schema and schema["enum"]:
        return sorted({json_type_name(v) for v in schema["enum"]})
    if "properties" in schema or "additionalProperties" in schema:
        return ["object"]
    if "items" in schema:
        return ["array"]
    return []


def is_not_only(schema: JsonSchema) -> bool:
    return "not" in schema and set(schema.keys()) <= {"not", "description", "title"}


def variants_of(schema: JsonSchema, root: JsonSchema) -> list[JsonSchema]:
    """anyOf/oneOf 변형 목록(해석 완료, `not` 전용 변형 제외)."""
    raw = schema.get("anyOf") or schema.get("oneOf") or []
    out = []
    for v in raw:
        r = resolve_ref(v, root)
        if is_not_only(r):
            continue
        out.append(r)
    return out


def variant_label(schema: JsonSchema) -> str:
    """anyOf 변형을 구분하는 짧은 라벨."""
    props = schema.get("properties", {})
    for key in ("source", "type"):
        p = props.get(key, {})
        if "const" in p:
            return f"{key}: {p['const']}"
        if "enum" in p and len(p["enum"]) == 1:
            return f"{key}: {p['enum'][0]}"
    req = schema.get("required")
    if req:
        return ", ".join(req)
    if "const" in schema:
        return f"const {json.dumps(schema['const'])}"
    if "enum" in schema:
        return "enum"
    types = schema_types(schema)
    if types:
        t = "/".join(types)
        if t == "array" and isinstance(schema.get("items"), dict):
            it = schema["items"].get("type")
            if isinstance(it, str):
                return f"array<{it}>"
        return t
    return schema.get("title") or schema.get("description", "")[:30] or "variant"


def first_sentence(text: str, limit: int = 140) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    # 문장 경계: 마침표 뒤 공백 + (대문자·괄호·따옴표·한글). "e.g. foo" 같은 소문자 이어짐은 자르지 않는다.
    m = re.search(r"(?<=[.!?])\s+(?=[A-Z(\"'가-힣])", text)
    head = text[: m.start()] if m else text
    if len(head) > limit:
        head = head[: limit - 1].rstrip() + "…"
    return head


def value_matches(schema: JsonSchema, value: Any, root: JsonSchema, depth: int = 0) -> bool:
    """가벼운 검증 휴리스틱: anyOf 변형 선택용. 완전한 JSON Schema 검증기는 아니다."""
    schema = resolve_ref(schema, root)
    if depth > 8:
        return True
    if is_not_only(schema):
        inner = schema["not"]
        return not value_matches(inner, value, root, depth + 1) if inner else False
    if "const" in schema:
        return value == schema["const"] and json_type_name(value) == json_type_name(schema["const"])
    if "enum" in schema and value not in schema["enum"]:
        return False
    types = schema_types(schema)
    vtype = json_type_name(value)
    if types:
        ok = vtype in types or (vtype == "integer" and "number" in types)
        if not ok:
            return False
    if "anyOf" in schema or "oneOf" in schema:
        if not any(value_matches(v, value, root, depth + 1) for v in variants_of(schema, root)):
            return False
    if vtype == "string" and isinstance(schema.get("pattern"), str):
        try:
            if not re.search(schema["pattern"], value):
                return False
        except re.error:
            pass
    if vtype == "object" and isinstance(value, dict):
        for req in schema.get("required", []):
            if req not in value:
                return False
        props = schema.get("properties", {})
        addl = schema.get("additionalProperties", True)
        for k, v in value.items():
            if k in props:
                if not value_matches(props[k], v, root, depth + 1):
                    return False
            elif addl is False:
                return False
            elif isinstance(addl, dict) and not value_matches(addl, v, root, depth + 1):
                return False
    if vtype == "array" and isinstance(value, list) and isinstance(schema.get("items"), dict):
        if not all(value_matches(schema["items"], v, root, depth + 1) for v in value):
            return False
    return True


def default_for(schema: JsonSchema, root: JsonSchema) -> Any:
    """편집기 초기값: schema.default → const → enum[0] → 타입별 빈 값."""
    schema = resolve_ref(schema, root)
    if "default" in schema:
        return schema["default"]
    if "const" in schema:
        return schema["const"]
    if "enum" in schema and schema["enum"]:
        return schema["enum"][0]
    types = schema_types(schema)
    if not types:
        vs = variants_of(schema, root)
        return default_for(vs[0], root) if vs else None
    t = types[0]
    return {"string": "", "boolean": False, "integer": 0, "number": 0.0, "array": [], "object": {}, "null": None}.get(t)
