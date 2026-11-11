"""스키마 로딩·$ref 해석·값 매칭 휴리스틱·env 레지스트리.

번들된 resources/claude-code-settings.schema.json 과 resources/env-vars.json 을 기본으로 쓰고,
load_schema(path) / load_env_registry(path) 로 외부 파일을 대신 쓸 수 있다.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Callable

from .constants import ENV_KEY, ENV_RESOURCE, OVERLAPS_RESOURCE, RESOURCE_DIR, SCHEMA_RESOURCE, Precedence

JsonSchema = dict[str, Any]


# --------------------------------------------------------------------------- 로딩
def _read_resource(name: str) -> str:
    return resources.files(__package__).joinpath(RESOURCE_DIR, name).read_text("utf-8")


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
        for name, prop in schema.get("properties", {}).get(ENV_KEY, {}).get("properties", {}).items():
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
            out.setdefault(e["env"], []).append((key, e.get("precedence", Precedence.RELATED)))
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


# --------------------------------------------------------------------------- 정규식·값 비교 (검증·편집기 공용)
_JS_NAMED_GROUP = re.compile(r"\(\?<(?![=!])")          # JS (?<name>…)  — (?<= (?<! 는 그대로
_JS_NAMED_BACKREF = re.compile(r"\\k<([A-Za-z_]\w*)>")  # JS \k<name>


@lru_cache(maxsize=1024)
def _compile(pattern: str) -> tuple[re.Pattern[str] | None, str]:
    py = _JS_NAMED_BACKREF.sub(r"(?P=\1)", _JS_NAMED_GROUP.sub("(?P<", pattern))
    try:
        return re.compile(py), ""
    except re.error as e:
        return None, str(e)


def compile_pattern(pattern: str) -> re.Pattern[str] | None:
    """스키마 pattern(ECMA 정규식)을 파이썬 re 로 컴파일(캐시). JS 전용 이름 그룹 문법은 바꾼다. 실패하면 None.

    JSON Schema 의 pattern 은 앵커가 없으면 부분 일치이므로 사용처는 .search() 를 쓴다.
    패키지의 모든 정규식 검사(검증·편집기·변형 선택)는 이 함수 하나를 거친다.
    """
    return _compile(pattern)[0]


def regex_error(pattern: str) -> str:
    """pattern 이 정규식으로 컴파일되지 않으면 오류 메시지, 되면 ""."""
    return _compile(pattern)[1]


def pattern_matches(pattern: str, value: str) -> bool:
    """value 가 pattern 에 (부분) 일치하는지. 컴파일할 수 없는 pattern 은 판단할 수 없으므로 True."""
    rx = compile_pattern(pattern)
    return rx is None or rx.search(value) is not None


def json_equal(a: Any, b: Any) -> bool:
    """JSON 값 동등성: true ≠ 1, 1 == 1.0, 배열·객체는 재귀 비교 (파이썬 == 는 True == 1 이다)."""
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(json_equal(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(json_equal(a[k], b[k]) for k in a)
    return type(a) is type(b) and a == b


def json_in(value: Any, options: list[Any]) -> bool:
    return any(json_equal(value, o) for o in options)


# --------------------------------------------------------------------------- 유틸
def find_inapplicable_paths(schema: JsonSchema, value: Any, root: JsonSchema, applicable: Callable[[str], bool],
                            path: str) -> list[str]:
    """value 안에서 applicable(경로) 가 False 인 중첩 키의 경로들(예: sandbox.enabledPlatforms)."""
    return prune_inapplicable(schema, value, root, applicable, path)[1]


def prune_inapplicable(schema: JsonSchema, value: Any, root: JsonSchema, applicable: Callable[[str], bool],
                       path: str, norm: str | None = None) -> tuple[Any, list[str]]:
    """value 에서 applicable(경로) 가 False 인 중첩 키를 뺀 사본과 뺀 키의 경로들. value 는 바꾸지 않는다.

    path 는 보고용 경로(배열 원소는 [i]), norm 은 applicable 에 넘기는 편집기 경로 표기
    (객체 'a.b', dict 값 'a.*', 배열 원소 'a[]'). 최상위 키 자체는 검사하지 않는다.
    """
    schema = resolve_ref(schema, root)
    norm = path if norm is None else norm
    if "anyOf" in schema or "oneOf" in schema:
        for v in variants_of(schema, root):
            if value_matches(v, value, root):
                return prune_inapplicable(v, value, root, applicable, path, norm)
        return value, []
    removed: list[str] = []
    if isinstance(value, dict):
        props = schema.get("properties", {})
        addl = schema.get("additionalProperties")
        kept: dict[str, Any] = {}
        for k, v in value.items():
            child = f"{path}.{k}"
            if k in props:
                if not applicable(f"{norm}.{k}"):
                    removed.append(child)
                    continue
                v, sub = prune_inapplicable(props[k], v, root, applicable, child, f"{norm}.{k}")
                removed += sub
            elif isinstance(addl, dict):
                v, sub = prune_inapplicable(addl, v, root, applicable, child, f"{norm}.*")
                removed += sub
            kept[k] = v
        return kept, removed
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        items: list[Any] = []
        for i, v in enumerate(value):
            v, sub = prune_inapplicable(schema["items"], v, root, applicable, f"{path}[{i}]", f"{norm}[]")
            items.append(v)
            removed += sub
        return items, removed
    return value, removed


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
    """가벼운 구조 일치 휴리스틱: anyOf 변형 선택용(타입·const·enum·required·pattern 정도).

    값의 문제를 찾는 검증은 validation.validate() 가 한다. 여기서 엄격하게 굴면 사소한 문제(범위 밖 숫자 등)가
    있는 값이 어느 변형에도 안 맞아 raw JSON 으로 떨어지므로 일부러 느슨하다.
    """
    schema = resolve_ref(schema, root)
    if depth > 8:
        return True
    if is_not_only(schema):
        inner = schema["not"]
        return not value_matches(inner, value, root, depth + 1) if inner else False
    if "const" in schema:
        return json_equal(value, schema["const"])
    if "enum" in schema and not json_in(value, schema["enum"]):
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
    if vtype == "string" and isinstance(schema.get("pattern"), str) and not pattern_matches(schema["pattern"], value):
        return False
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


def default_for(schema: JsonSchema, root: JsonSchema, _depth: int = 0) -> Any:
    """편집기 초기값: schema.default → const → enum[0] → 타입별 빈 값.

    숫자는 범위 안으로 옮긴 0, 객체는 required 키를 각자의 기본값으로 채운 dict(새 항목이 처음부터 필수 키를 갖게).
    """
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
        return default_for(vs[0], root, _depth + 1) if vs and _depth < 8 else None
    t = types[0]
    if t in ("integer", "number"):
        return _clamp_zero(schema, integer=t == "integer")
    if t == "object" and _depth < 8:
        props = schema.get("properties", {})
        return {k: default_for(props[k], root, _depth + 1) for k in schema.get("required", []) if k in props}
    return {"string": "", "boolean": False, "array": [], "object": {}, "null": None}.get(t)


def _clamp_zero(schema: JsonSchema, integer: bool) -> int | float:
    """숫자 기본값: 0 을 스키마 범위(minimum/maximum/exclusive*) 안으로 옮긴 값."""
    def num(k: str) -> float | None:
        x = schema.get(k)
        return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None

    step = 1 if integer else 0.001
    lo, xlo, hi, xhi = num("minimum"), num("exclusiveMinimum"), num("maximum"), num("exclusiveMaximum")
    v: float = 0
    if lo is not None and v < lo:
        v = lo
    if xlo is not None and v <= xlo:
        v = xlo + step
    if hi is not None and v > hi:
        v = hi
    if xhi is not None and v >= xhi:
        v = xhi - step
    return int(v) if integer else float(v)
