"""설정 값 검증 — 번들 스키마(JSON Schema draft-07 중 이 스키마가 쓰는 부분 + 확장 format)로 값을 검사한다.

검증은 **막지 않는다.** 편집기·API·저장은 값을 바꾸지 않고 그대로 받아 보존하고, 문제는 Issue 목록으로 돌려준다.
위젯은 그 목록을 툴바 ⚠ 버튼·행 아래 메시지로 보여 주고, 공개 API 는 SettingValidationWarning(파이썬 warnings)으로
알린다. 값을 바꾸기 **전에** 막고 싶으면(엄격 모드) 호출하는 쪽에서
``warnings.simplefilter("error", SettingValidationWarning)`` 를 켠다.

지원 키워드: type, enum, const, anyOf/oneOf, allOf, not, properties, patternProperties, required,
additionalProperties, propertyNames, min/maxProperties, items, min/maxItems, uniqueItems, min/maxLength, pattern,
format(constants.Format), minimum/maximum/exclusiveMinimum/exclusiveMaximum, multipleOf, x-disjointNetworks.
oneOf 는 스키마스토어 변형들이 서로 겹치는 경우가 있어 anyOf 처럼 "하나 이상 일치"로 본다.
"""
from __future__ import annotations

import ipaddress
import json
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable, Iterable
from urllib.parse import urlsplit

from .constants import DISJOINT_NETWORKS, ENV_KEY, Format, Severity
from .i18n import join_path, tr
from .schema import (
    JsonSchema,
    compile_pattern,
    json_equal,
    json_in,
    json_type_name,
    regex_error,
    resolve_ref,
    value_matches,
    variant_label,
)

__all__ = ["Issue", "SettingValidationWarning", "validate", "validate_settings", "is_valid", "errors_only"]

MAX_DEPTH = 24
MAX_LISTED = 6  # 메시지에 나열할 허용값·문제 수


# --------------------------------------------------------------------------- 결과 타입
@dataclass(frozen=True)
class Issue:
    """검증 문제 하나. path 는 최상위 키부터의 경로("permissions.allow[2]", "env.API_TIMEOUT_MS")."""

    path: str
    message: str
    severity: Severity = Severity.ERROR
    keyword: str = ""  # 위반한 스키마 키워드(type, enum, pattern, format …)

    @property
    def key(self) -> str:
        """문제가 속한 최상위 설정 키."""
        return re.split(r"[.\[]", self.path, maxsplit=1)[0]

    def __str__(self) -> str:
        return f"{self.path}: {self.message}" if self.path else self.message


class SettingValidationWarning(UserWarning):
    """API 로 넣거나 저장하는 설정에 스키마 문제가 있을 때. .issues 에 Issue 목록이 있다."""

    def __init__(self, issues: Iterable[Issue]):
        self.issues = list(issues)
        shown = "; ".join(str(i) for i in self.issues[:MAX_LISTED])
        if len(self.issues) > MAX_LISTED:
            shown += " " + tr("(+{n} more)", n=len(self.issues) - MAX_LISTED)
        super().__init__(tr("{n} problem(s) in settings: {issues}", n=len(self.issues), issues=shown))


def errors_only(issues: Iterable[Issue]) -> list[Issue]:
    return [i for i in issues if i.severity is Severity.ERROR]


# --------------------------------------------------------------------------- 진입점
def validate(schema: JsonSchema, value: Any, root: JsonSchema, path: str = "") -> list[Issue]:
    """schema 에 대한 value 의 문제 목록(없으면 빈 목록). root 는 $ref 해석용 전체 스키마."""
    out: list[Issue] = []
    _check(schema, value, root, path, out, 0)
    return out


def is_valid(schema: JsonSchema, value: Any, root: JsonSchema) -> bool:
    """ERROR 가 없으면 True(WARNING 은 무시)."""
    return not errors_only(validate(schema, value, root))


def validate_settings(data: dict[str, Any], schema: JsonSchema) -> list[Issue]:
    """settings.json 문서 전체 검증. 스키마 밖 최상위 키는 WARNING(미래 버전 키일 수 있다).

    env 변수 값이 스키마 enum 밖이면 WARNING 으로 낮춘다 — Claude Code 는 "1"/"true" 처럼 느슨하게 읽는데
    스키마스토어 enum 은 보수적으로 ["0", "1"] 만 적은 경우가 많다.
    """
    props = schema.get("properties", {})
    out: list[Issue] = []
    for key, value in data.items():
        if key not in props:
            out.append(Issue(key, tr("Unknown setting key (not in the bundled schema)"), Severity.WARNING,
                             "additionalProperties"))
            continue
        issues = validate(props[key], value, schema, key)
        if key == ENV_KEY:
            issues = [Issue(i.path, i.message, Severity.WARNING, i.keyword) if i.keyword in ("enum", "const") else i
                      for i in issues]
        out += issues
    return out


# --------------------------------------------------------------------------- 키워드 검사
def _add(out: list[Issue], path: str, keyword: str, message: str, severity: Severity = Severity.ERROR) -> None:
    out.append(Issue(path, message, severity, keyword))


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _short(value: Any, limit: int = 40) -> str:
    return _clip(json.dumps(value, ensure_ascii=False), limit)


def _listing(values: list[Any]) -> str:
    text = ", ".join(_short(v) for v in values[:MAX_LISTED])
    return text + (", …" if len(values) > MAX_LISTED else "")


def _declared_types(schema: JsonSchema) -> list[str]:
    t = schema.get("type")
    return [t] if isinstance(t, str) else [x for x in t if isinstance(x, str)] if isinstance(t, list) else []


def _type_ok(value: Any, types: list[str]) -> bool:
    vtype = json_type_name(value)
    if vtype in types:
        return True
    if vtype == "integer" and "number" in types:
        return True
    return vtype == "number" and "integer" in types and float(value).is_integer()


def _check(schema: JsonSchema, value: Any, root: JsonSchema, path: str, out: list[Issue], depth: int) -> None:
    schema = resolve_ref(schema, root)
    if depth > MAX_DEPTH or not schema:
        return
    if isinstance(schema.get("not"), dict) and schema["not"]:
        if not errors_only(_collect(schema["not"], value, root, path, depth + 1)):
            _add(out, path, "not", tr("This value is not allowed here"))
    for sub in schema.get("allOf", []):
        _check(sub, value, root, path, out, depth + 1)
    if "anyOf" in schema or "oneOf" in schema:
        _check_variants(schema, value, root, path, out, depth)
    if "const" in schema and not json_equal(value, schema["const"]):
        _add(out, path, "const", tr("Must be {value}", value=_short(schema["const"])))
        return
    if "enum" in schema and not json_in(value, schema["enum"]):
        _add(out, path, "enum", tr("Not an allowed value. Allowed: {values}", values=_listing(schema["enum"])))
        return
    types = _declared_types(schema)
    if types and not _type_ok(value, types):
        _add(out, path, "type", tr("Expected {expected}, got {actual}", expected=" | ".join(types),
                                   actual=json_type_name(value)))
        return
    if isinstance(value, str):
        _check_string(schema, value, path, out)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        _check_number(schema, value, path, out)
    elif isinstance(value, dict):
        _check_object(schema, value, root, path, out, depth)
    elif isinstance(value, list):
        _check_array(schema, value, root, path, out, depth)


def _collect(schema: JsonSchema, value: Any, root: JsonSchema, path: str, depth: int) -> list[Issue]:
    out: list[Issue] = []
    _check(schema, value, root, path, out, depth)
    return out


def _check_variants(schema: JsonSchema, value: Any, root: JsonSchema, path: str, out: list[Issue],
                    depth: int) -> None:
    variants = [resolve_ref(v, root) for v in (schema.get("anyOf") or schema.get("oneOf") or [])]
    results: list[tuple[JsonSchema, list[Issue]]] = []
    for v in variants:
        issues = _collect(v, value, root, path, depth + 1)
        if not errors_only(issues):
            out.extend(issues)  # 맞는 변형의 WARNING 은 그대로 전달
            return
        results.append((v, issues))
    # 어느 변형에도 맞지 않음: 사용자가 의도한 변형을 추정해 그 변형의 문제를 보여 준다
    pick = next((r for r in results if value_matches(r[0], value, root)), None)
    if pick is None:
        pick = _best_by_discriminator(results, value, root)
    if pick is None:
        typed = [r for r in results if not _declared_types(r[0]) or _type_ok(value, _declared_types(r[0]))]
        pick = typed[0] if len(typed) == 1 else None
    if pick is not None:
        out.extend(pick[1])
        return
    _add(out, path, "anyOf", tr("Does not match any allowed form: {forms}",
                                forms=" / ".join(_describe_variant(v) for v, _ in results)))


def _best_by_discriminator(results: list[tuple[JsonSchema, list[Issue]]], value: Any,
                           root: JsonSchema) -> tuple[JsonSchema, list[Issue]] | None:
    """객체 값의 판별 필드(type: "http" 처럼 const 인 속성)가 맞는 변형이 하나뿐이면 그 변형."""
    if not isinstance(value, dict):
        return None
    hits = []
    for r in results:
        props = r[0].get("properties", {})
        consts = {k: resolve_ref(p, root)["const"] for k, p in props.items() if "const" in resolve_ref(p, root)}
        if consts and all(k in value and json_equal(value[k], c) for k, c in consts.items()):
            hits.append(r)
    return hits[0] if len(hits) == 1 else None


def _describe_variant(v: JsonSchema) -> str:
    if "const" in v:
        return _short(v["const"])
    if "enum" in v:
        return _listing(v["enum"])
    if isinstance(v.get("pattern"), str):
        return tr("pattern {pattern}", pattern=_clip(v["pattern"], 60))
    return variant_label(v)


def _check_string(schema: JsonSchema, value: str, path: str, out: list[Issue]) -> None:
    lo, hi = schema.get("minLength"), schema.get("maxLength")
    if isinstance(lo, int) and len(value) < lo:
        _add(out, path, "minLength", tr("Must not be empty") if lo == 1 else
             tr("Must be at least {n} characters", n=lo))
    if isinstance(hi, int) and len(value) > hi:
        _add(out, path, "maxLength", tr("Must be at most {n} characters", n=hi))
    pattern = schema.get("pattern")
    if isinstance(pattern, str):
        rx = compile_pattern(pattern)
        if rx is not None and rx.search(value) is None:
            _add(out, path, "pattern", tr("Does not match the pattern {pattern}", pattern=_clip(pattern, 60)))
    fmt = schema.get("format")
    checker = _FORMATS.get(fmt) if isinstance(fmt, str) else None
    if checker is not None:
        message = checker(value)
        if message:
            _add(out, path, "format", message, Severity.WARNING if fmt in _SOFT_FORMATS else Severity.ERROR)


def _check_number(schema: JsonSchema, value: float, path: str, out: list[Issue]) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        _add(out, path, "type", tr("Must be a finite number"))
        return
    lo, hi = _num(schema.get("minimum")), _num(schema.get("maximum"))
    xlo, xhi = _num(schema.get("exclusiveMinimum")), _num(schema.get("exclusiveMaximum"))
    if schema.get("exclusiveMinimum") is True:  # draft-04 불리언 형식
        xlo, lo = lo, None
    if schema.get("exclusiveMaximum") is True:
        xhi, hi = hi, None
    if lo is not None and value < lo:
        _add(out, path, "minimum", tr("Must be ≥ {n}", n=lo))
    if xlo is not None and value <= xlo:
        _add(out, path, "exclusiveMinimum", tr("Must be > {n}", n=xlo))
    if hi is not None and value > hi:
        _add(out, path, "maximum", tr("Must be ≤ {n}", n=hi))
    if xhi is not None and value >= xhi:
        _add(out, path, "exclusiveMaximum", tr("Must be < {n}", n=xhi))
    step = _num(schema.get("multipleOf"))
    if step is not None and step > 0 and not math.isclose(value / step, round(value / step), abs_tol=1e-9):
        _add(out, path, "multipleOf", tr("Must be a multiple of {n}", n=step))


def _num(x: Any) -> float | None:
    """스키마 숫자 키워드 값. 숫자가 아니면(불리언 포함) None."""
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def _check_object(schema: JsonSchema, value: dict[str, Any], root: JsonSchema, path: str, out: list[Issue],
                  depth: int) -> None:
    props = schema.get("properties", {})
    for req in schema.get("required", []):
        if req not in value:
            _add(out, path, "required", tr("Missing required key \"{key}\"", key=req))
    names = schema.get("propertyNames")
    addl = schema.get("additionalProperties", True)
    pattern_props = schema.get("patternProperties", {})
    for k, v in value.items():
        child = join_path(path, k)
        if isinstance(names, dict):
            bad = errors_only(_collect(names, k, root, child, depth + 1))
            if bad:
                _add(out, child, "propertyNames", tr("Invalid key \"{key}\": {reason}", key=k, reason=bad[0].message))
        if k in props:
            _check(props[k], v, root, child, out, depth + 1)
            continue
        matched = [sub for pat, sub in pattern_props.items() if (rx := compile_pattern(pat)) and rx.search(k)]
        for sub in matched:
            _check(sub, v, root, child, out, depth + 1)
        if matched:
            continue
        if addl is False:
            _add(out, child, "additionalProperties", tr("Unknown key \"{key}\"", key=k))
        elif isinstance(addl, dict):
            _check(addl, v, root, child, out, depth + 1)
    lo, hi = schema.get("minProperties"), schema.get("maxProperties")
    if isinstance(lo, int) and len(value) < lo:
        _add(out, path, "minProperties", tr("Must have at least {n} entries", n=lo))
    if isinstance(hi, int) and len(value) > hi:
        _add(out, path, "maxProperties", tr("Must have at most {n} entries", n=hi))


def _check_array(schema: JsonSchema, value: list[Any], root: JsonSchema, path: str, out: list[Issue],
                 depth: int) -> None:
    items = schema.get("items")
    if isinstance(items, dict):
        for i, v in enumerate(value):
            _check(items, v, root, f"{path}[{i}]", out, depth + 1)
    elif isinstance(items, list):
        for i, (sub, v) in enumerate(zip(items, value)):
            _check(sub, v, root, f"{path}[{i}]", out, depth + 1)
    lo, hi = schema.get("minItems"), schema.get("maxItems")
    if isinstance(lo, int) and len(value) < lo:
        _add(out, path, "minItems", tr("Must have at least {n} items", n=lo))
    if isinstance(hi, int) and len(value) > hi:
        _add(out, path, "maxItems", tr("Must have at most {n} items", n=hi))
    if schema.get("uniqueItems") is True:
        for j, v in enumerate(value):
            i = next((i for i in range(j) if json_equal(value[i], v)), None)
            if i is not None:
                _add(out, f"{path}[{j}]", "uniqueItems", tr("Duplicate of item {i}", i=i))
    if schema.get(DISJOINT_NETWORKS) is True:
        _check_disjoint(value, path, out)


def _check_disjoint(value: list[Any], path: str, out: list[Issue]) -> None:
    nets: list[tuple[int, ipaddress.IPv4Network]] = []
    for j, v in enumerate(value):
        try:
            net = ipaddress.IPv4Network(v, strict=False) if isinstance(v, str) else None
        except ValueError:
            net = None
        if net is None:
            continue
        for i, other in nets:
            if net.overlaps(other):
                _add(out, f"{path}[{j}]", DISJOINT_NETWORKS, tr("Overlaps item {i} ({other})", i=i, other=str(other)))
                break
        nets.append((j, net))


# --------------------------------------------------------------------------- format
_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*")
_HOST_REQUIRED = {"http", "https", "ws", "wss"}
_SEMVER = re.compile(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?")
# 공인 주소로 쓸 수 없는 IPv4 블록(IANA special-purpose: 사설·공유(CGNAT/VPN)·루프백·링크로컬·문서용·벤치마크·멀티캐스트·예약)
_NON_PUBLIC = tuple(ipaddress.IPv4Network(n) for n in (
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12", "192.0.0.0/24",
    "192.0.2.0/24", "192.88.99.0/24", "192.168.0.0/16", "198.18.0.0/15", "198.51.100.0/24", "203.0.113.0/24",
    "224.0.0.0/4", "240.0.0.0/4"))


def _check_uri(value: str) -> str:
    parts = urlsplit(value) if value and not any(c.isspace() for c in value) else None
    ok = parts is not None and bool(_SCHEME.fullmatch(parts.scheme or "")) and bool(parts.netloc or parts.path)
    if ok and parts is not None and parts.scheme.lower() in _HOST_REQUIRED:
        ok = bool(parts.hostname)
    return "" if ok else tr("Not a valid URL (e.g. https://example.com/path)")


def _check_uri_pattern(value: str) -> str:
    return _check_uri(value.replace("*", "x"))


def _check_regex(value: str) -> str:
    err = regex_error(value)
    return tr("Not a valid regular expression: {error}", error=err) if err else ""


def _check_semver(value: str) -> str:
    return "" if _SEMVER.fullmatch(value) else tr("Not a valid version number (e.g. 2.1.100)")


@lru_cache(maxsize=1)
def _time_zones() -> frozenset[str]:
    try:
        import zoneinfo

        return frozenset(zoneinfo.available_timezones())
    except Exception:  # noqa: BLE001 — tzdata 가 없는 환경(Windows 기본)
        return frozenset()


def _check_time_zone(value: str) -> str:
    zones = _time_zones()
    if not zones:  # 이 환경에서는 확인할 수 없다
        return ""
    return "" if value in zones else tr("Unknown IANA time zone name (e.g. UTC, Europe/Dublin)")


def _check_public_cidr(value: str) -> str:
    if "/" not in value:
        return tr("Write a CIDR block with a prefix length (e.g. 198.51.100.0/24)")
    try:
        net = ipaddress.IPv4Network(value, strict=True)
    except ValueError as e:
        return tr("Not a valid IPv4 CIDR block: {error}", error=e)
    if not 8 <= net.prefixlen <= 32:
        return tr("Prefix length must be /8 to /32")
    bad = next((n for n in _NON_PUBLIC if net.overlaps(n)), None)
    if bad is not None:
        return tr("Overlaps non-public address space {range}", range=str(bad))
    return ""


_FORMATS: dict[str, Callable[[str], str]] = {
    Format.URI: _check_uri,
    Format.URI_PATTERN: _check_uri_pattern,
    Format.REGEX: _check_regex,
    Format.SEMVER: _check_semver,
    Format.TIME_ZONE: _check_time_zone,
    Format.PUBLIC_IPV4_CIDR: _check_public_cidr,
}
_SOFT_FORMATS = {Format.TIME_ZONE, Format.REGEX}  # 이 환경과 Claude Code(JS)의 판단이 다를 수 있어 WARNING
