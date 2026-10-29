"""생성 코드 작성: keys.py(SettingKey + NESTED_SETTINGS), env_keys.py(EnvVar), _version.py."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .pkg import PKG, JsonType, Scope, Topic, Version

KEYS_OUT = PKG / "keys.py"
ENV_KEYS_OUT = PKG / "env_keys.py"
VERSION_OUT = PKG / "_version.py"
WIDTH = 120
# SettingKey 의 속성/메서드, 클래스 본문에서 참조하는 이름 — 멤버 이름으로 쓰면 가려진다
RESERVED = {"info", "coerce", "JsonType", "Scope", "SettingInfo", "Topic", "Version"}


def enum_member_name(key: str) -> str:
    """키 → enum 멤버 이름. 식별자면 그대로, 아니면 특수문자를 '_' 로 바꾼다 ($schema → schema)."""
    name = key if key.isidentifier() else (re.sub(r"\W+", "_", key).strip("_") or "_")
    if name in RESERVED:
        raise ValueError(f"setting key {key!r} collides with a SettingKey attribute")
    return name


def _flags(value, cls) -> str:
    """플래그 값 → 'Scope.USER | Scope.MANAGED' (단일 비트 멤버를 정의 순서로)."""
    bits = [m for m in cls if m.value and m.value & (m.value - 1) == 0 and m in value]
    return " | ".join(f"{cls.__name__}.{m.name}" for m in bits)


def _py(v: Any) -> str:
    """메타데이터 값 → 파이썬 식. 상수(Scope·JsonType·Topic·Version)는 이름으로, JSON 값은 리터럴로(문자열은 큰따옴표)."""
    if isinstance(v, Scope):
        return _flags(v, Scope)
    if isinstance(v, JsonType):
        return _flags(v, JsonType)
    if isinstance(v, Topic):
        return f"Topic.{v.name}"
    if isinstance(v, Version):
        return f"Version({v.major}, {v.minor}, {v.patch})"
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, tuple):
        inner = ", ".join(_py(x) for x in v)
        return f"({inner},)" if len(v) == 1 else f"({inner})"
    if isinstance(v, list):
        return "[" + ", ".join(_py(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ", ".join(f"{_py(k)}: {_py(x)}" for k, x in v.items()) + "}"
    return repr(v)


def info_args(key: str, info: dict, replaced_by: str | None = None) -> list[str]:
    """SettingInfo(...) 인자 식 목록. replaced_by 는 대체 키의 SettingInfo 를 가리키는 식(이름 참조)."""
    args = [_py(key)]
    if info["scope"] != Scope.ANY_FILE:
        args.append(f"scope={_py(info['scope'])}")
    if info["type"]:
        args.append(f"type={_py(info['type'])}")
    for field in ("default", "values", "since"):
        if info[field] not in (None, ()):
            args.append(f"{field}={_py(info[field])}")
    if info["deprecated"]:
        args.append("deprecated=True")
    if info["deprecated_since"]:
        args.append(f"deprecated_since={_py(info['deprecated_since'])}")
    if replaced_by:
        args.append(f"replaced_by={replaced_by}")
    for field in ("removed", "topic"):
        if info[field]:
            args.append(f"{field}={_py(info[field])}")
    for field in ("in_docs", "in_schemastore"):
        if not info[field]:
            args.append(f"{field}=False")
    return args


def top_order(top: dict[str, dict]) -> list[str]:
    """대체 키가 먼저 정의되도록 deprecated 키를 대체 키 바로 뒤로 옮긴 순서(클래스 본문에서 이름으로 참조하므로)."""
    order = list(top)
    for key, info in top.items():
        target = info["replaced_by"]
        if target is None:
            continue
        if target not in top:
            raise ValueError(f"{key}: replaced_by {target!r} is not a top-level setting key")
        if order.index(target) > order.index(key):
            order.remove(key)
            order.insert(order.index(target) + 1, key)
    for key in order:
        target = top[key]["replaced_by"]
        if target is not None and order.index(target) > order.index(key):
            raise ValueError(f"{key}: replacement chain through {target!r} cannot be ordered")
    return order


def _nested_replacement(path: str, info: dict, top: dict[str, dict]) -> str | None:
    target = info["replaced_by"]
    if target is None:
        return None
    if target not in top:
        raise ValueError(f"{path}: replaced_by {target!r} is not a top-level setting key")
    return f"SettingKey.{enum_member_name(target)}.info"


def _wrap(head: str, args: list[str], tail: str, indent: str) -> list[str]:
    """head + 'SettingInfo(' + args + ')' + tail 을 WIDTH 안에서 줄바꿈."""
    one = f"{head}SettingInfo({', '.join(args)}){tail}"
    if len(one) <= WIDTH:
        return [one]
    lines, cur = [f"{head}SettingInfo("], indent + "    "
    for i, a in enumerate(args):
        piece = a + (", " if i < len(args) - 1 else f"){tail}")
        if len(cur) + len(piece.rstrip()) > WIDTH and cur.strip():
            lines.append(cur.rstrip())
            cur = indent + "    "
        cur += piece
    lines.append(cur.rstrip())
    return lines


def write_keys_module(top: dict[str, dict], nested: dict[str, dict], version: str) -> Path:
    lines = [
        f'"""설정 키 enum + 키별 메타데이터 — Claude Code v{version} 기준.',
        "",
        "tools/refresh_resources.py 가 공식 문서(settings-reference)·schemastore 스키마·CHANGELOG 에서 자동 생성한다.",
        "직접 수정하지 말 것: 보정은 tools/resource_overrides.json 에 적고 다시 생성한다.",
        "",
        "멤버 이름이 곧 키다: SettingKey.model == \"model\". 식별자가 될 수 없는 키만 이름이 다르다",
        "(SettingKey.schema.value == \"$schema\"). 각 멤버의 .info 가 SettingInfo(스코프·타입·기본값·값 후보·버전).",
        "중첩 경로(sandbox.bwrapPath 등)의 메타데이터는 NESTED_SETTINGS, 통합 조회는 setting_info(path).",
        "스코프·타입·주제는 constants 의 enum, 버전은 Version 으로 적고 문자열은 키와 JSON 값(기본값·값 후보)에만 쓴다.",
        '"""',
        "from __future__ import annotations",
        "",
        "from .constants import JsonType, Scope, Topic",
        "from .env_keys import EnvVar",
        "from .spec import KeyEnum, SettingInfo, Version",
        "",
        "",
        "class SettingKey(KeyEnum):",
        '    """settings.json 최상위 키."""',
        "",
        "    @property",
        "    def info(self) -> SettingInfo:",
        "        assert self._info is not None",
        "        return self._info",
        "",
    ]
    for key in top_order(top):
        info = top[key]
        replaced_by = enum_member_name(info["replaced_by"]) if info["replaced_by"] else None
        lines += _wrap(f"    {enum_member_name(key)} = ", info_args(key, info, replaced_by), "", "    ")
    lines += ["", "", "NESTED_SETTINGS: dict[str, SettingInfo] = {info.key: info for info in ("]
    for path, info in nested.items():
        lines += _wrap("    ", info_args(path, info, _nested_replacement(path, info, top)), ",", "    ")
    lines += [
        ")}",
        "",
        "",
        "def setting_info(path: str) -> SettingInfo | None:",
        '    """최상위 키 또는 중첩 경로("sandbox.bwrapPath")의 SettingInfo. 모르는 경로는 None."""',
        "    member = SettingKey._value2member_map_.get(path)",
        "    return member.info if isinstance(member, SettingKey) else NESTED_SETTINGS.get(path)",
        "",
        "",
        '__all__ = ["KeyEnum", "SettingInfo", "SettingKey", "EnvVar", "NESTED_SETTINGS", "setting_info"]',
        "",
    ]
    KEYS_OUT.write_text("\n".join(lines), "utf-8")
    return KEYS_OUT


def write_env_keys_module(env_names: list[str]) -> Path:
    lines = [
        '"""env 블록의 환경변수 이름 enum (tools/refresh_resources.py 가 스키마·문서·overrides 에서 자동 생성 — 직접 수정하지 말 것).',
        "",
        "멤버 이름이 곧 변수 이름이다: EnvVar.API_TIMEOUT_MS == \"API_TIMEOUT_MS\". 설명·값 후보는 resources/env-vars.json.",
        '"""',
        "from __future__ import annotations",
        "",
        "from .spec import KeyEnum",
        "",
        "",
        "class EnvVar(KeyEnum):",
        '    """settings.json env 블록의 환경변수 이름(스키마 + 문서 + overrides)."""',
        "",
    ]
    lines += [f"    {enum_member_name(n)} = {_py(n)}" for n in env_names]
    lines += ["", "", '__all__ = ["EnvVar"]', ""]
    ENV_KEYS_OUT.write_text("\n".join(lines), "utf-8")
    return ENV_KEYS_OUT


def write_version_module(version: str) -> Path:
    VERSION_OUT.write_text(
        '"""패키지 버전 = 번들 리소스를 생성한 Claude Code 버전 (tools/refresh_resources.py 가 CHANGELOG 최신 버전으로 갱신)."""\n'
        f'__version__ = "{version}"\n', "utf-8")
    return VERSION_OUT
