"""설정 키 메타데이터의 타입 정의: Version, SettingInfo, KeyEnum.

keys.py / env_keys.py(자동 생성)가 이 모듈과 constants.py 만 임포트한다(Qt 의존 없음).
SettingKey 의 각 멤버는 SettingInfo 를 값으로 가지며, 멤버 자체는 여전히 실제 키 문자열로 동작한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, NamedTuple

from .constants import JsonType, Scope, Topic

__all__ = ["KeyEnum", "SettingInfo", "Version"]

_VERSION = re.compile(r"^v?(\d+(?:\.\d+){0,2})$")


# --------------------------------------------------------------------------- 버전
class Version(NamedTuple):
    """Claude Code 버전. 튜플이라 그대로 비교되고, str() 은 '2.1.283'."""

    major: int
    minor: int = 0
    patch: int = 0

    @classmethod
    def parse(cls, text: str | Version) -> Version:
        """'2.1.283' / 'v2.1' → Version(2, 1, 283) / Version(2, 1, 0). 형식이 틀리면 ValueError."""
        if isinstance(text, Version):
            return text
        m = _VERSION.match(str(text).strip())
        if not m:
            raise ValueError(f"invalid version: {text!r}")
        return cls(*(int(p) for p in m.group(1).split(".")))

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


# --------------------------------------------------------------------------- 키 메타데이터
@dataclass(frozen=True)
class SettingInfo:
    """설정 키(또는 중첩 경로) 하나의 메타데이터. tools/refresh_resources.py 가 문서·스키마·CHANGELOG 에서 생성한다.

    since / removed / deprecated_since 가 None 이면 '버전 미상' — 버전 필터에서 항상 있는 것으로 취급한다.
    values 는 값 후보(배열 키면 원소 후보), default 는 문서·스키마에 적힌 기본값(None = 미설정/미상).
    replaced_by 는 대체 키의 SettingInfo.
    """

    key: str
    scope: Scope = Scope.ANY_FILE
    type: JsonType = JsonType.NONE
    default: Any = None
    values: tuple[Any, ...] = ()
    since: Version | None = None
    deprecated: bool = False
    deprecated_since: Version | None = None
    replaced_by: SettingInfo | None = None
    removed: Version | None = None
    topic: Topic | None = None
    in_docs: bool = True
    in_schemastore: bool = True

    def allowed_in(self, scope: Scope) -> bool:
        """scope 중 하나라도 이 키가 효력을 갖는 파일이면 True."""
        return bool(self.scope & scope)

    def available_in(self, version: Version | str | None) -> bool:
        """그 버전의 Claude Code 에 이 키가 있는지. version 이 None 이면 항상 True."""
        if version is None:
            return True
        v = Version.parse(version)
        if self.since is not None and v < self.since:
            return False
        return self.removed is None or v < self.removed

    def applicable(self, scope: Scope, version: Version | str | None) -> bool:
        """편집 대상 파일(scope)과 Claude Code 버전에서 이 키가 효력을 갖는지(allowed_in ∧ available_in)."""
        return self.allowed_in(scope) and self.available_in(version)

    def deprecated_in(self, version: Version | str | None) -> bool:
        """그 버전에서 deprecated 상태인지. 버전이 None 이거나 deprecated 시점이 미상이면 deprecated 여부 그대로."""
        if not self.deprecated:
            return False
        if version is None or self.deprecated_since is None:
            return True
        return Version.parse(version) >= self.deprecated_since


# --------------------------------------------------------------------------- 키 enum 베이스
class KeyEnum(str, Enum):
    """str 겸용 enum: dict 키·비교·f-string 모두 실제 키 문자열로 동작한다.

    멤버 값으로 SettingInfo 를 주면 키 문자열은 info.key 가 되고, info 는 멤버의 .info 로 꺼낸다.
    """

    _info: SettingInfo | None

    def __new__(cls, value: str | SettingInfo):
        key = value.key if isinstance(value, SettingInfo) else value
        obj = str.__new__(cls, key)
        obj._value_ = key
        obj._info = value if isinstance(value, SettingInfo) else None
        return obj

    def __str__(self) -> str:
        return str(self.value)

    def __format__(self, spec: str) -> str:
        return format(str(self.value), spec)

    @classmethod
    def coerce(cls, key: object) -> str:
        """enum 멤버·멤버 이름·키 문자열 → 실제 키 문자열."""
        if isinstance(key, Enum):
            return str(key.value)
        text = str(key)
        member = cls.__members__.get(text)  # 멤버 이름
        return str(member.value) if member is not None else text
