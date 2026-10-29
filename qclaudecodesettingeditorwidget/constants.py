"""패키지 전역에서 참조하는 상수 — 문자열 리터럴은 여기서 한 번만 정의하고 다른 모듈·생성 코드는 이름으로 참조한다.

Qt 와 패키지 내부 모듈에 의존하지 않으므로 tools/ 스크립트도 이 파일을 단독으로 로드한다.
"""
from __future__ import annotations

import re
from enum import Enum, IntFlag, auto

APP_ID = "qccse"

# --------------------------------------------------------------------------- settings.json · 페이지
ENV_KEY = "env"            # settings.json 의 env 블록 키 (SettingKey.env 와 같은 문자열)
ENV_ID = ENV_KEY           # env 편집 페이지 id
OTHER_ID = "other"         # 미분류 키 페이지 id
JSON_ID = "json"           # 원문 JSON 페이지 id

# --------------------------------------------------------------------------- 번들 리소스
RESOURCE_DIR = "resources"
SCHEMA_RESOURCE = "claude-code-settings.schema.json"
ENV_RESOURCE = "env-vars.json"
OVERLAPS_RESOURCE = "overlaps.json"

# --------------------------------------------------------------------------- 현지화
LOCALE_DIR = "locales"
LOCALE_FILE_PREFIX = f"{APP_ID}_"                # locales/qccse_<lang>.ts|.qm
CONTEXT_UI = APP_ID                             # UI 문자열 번역 컨텍스트
CONTEXT_SCHEMA = "schema"                       # 스키마 설명 번역 컨텍스트(소스 = 설정 경로)
SOURCE_LANG = "en"
ENV_LANG = f"{APP_ID.upper()}_LANG"             # 언어 강제 환경변수
ENV_LOCALE_DIR = f"{APP_ID.upper()}_LOCALE_DIR"  # 추가 번역 디렉터리 환경변수

# --------------------------------------------------------------------------- 공용 스타일
MUTED_COLOR = "#8a8a8a"
MUTED = f"color: {MUTED_COLOR};"
INVALID_STYLE = "border: 1px solid #d33; background: #fff4f4;"


def _parse_flags(cls, text: str):
    """"user|managed" / "string, null" → 플래그 합. 알 수 없는 이름은 KeyError."""
    out = cls(0)
    for part in re.split(r"[|,]", text):
        if part.strip():
            out |= cls[part.strip().upper().replace(" ", "_")]
    return out


# --------------------------------------------------------------------------- 키 메타데이터
class Scope(IntFlag):
    """키가 효력을 갖는 설정 파일. 문서(settings-reference)의 Scope 열을 비트 플래그로 옮긴 것."""

    NONE = 0
    USER = auto()           # ~/.claude/settings.json
    PROJECT = auto()        # .claude/settings.json
    LOCAL = auto()          # .claude/settings.local.json
    MANAGED = auto()        # 관리형(정책) 설정
    GLOBAL_CONFIG = auto()  # ~/.claude.json — settings.json 이 아니므로 편집 대상에서 제외
    ANY_FILE = USER | PROJECT | LOCAL | MANAGED

    @classmethod
    def parse(cls, text: str) -> Scope:
        return _parse_flags(cls, text)


class JsonType(IntFlag):
    """키 값의 JSON 타입(스키마 type). 유니온 타입은 비트 합(STRING | NULL)."""

    NONE = 0
    NULL = auto()
    BOOLEAN = auto()
    INTEGER = auto()
    NUMBER = auto()
    STRING = auto()
    ARRAY = auto()
    OBJECT = auto()

    @classmethod
    def parse(cls, text: str) -> JsonType:
        return _parse_flags(cls, text)


class Topic(str, Enum):
    """settings-reference 문서의 주제(색인표 Topic 열). 문서에 새 주제가 생기면 여기에 추가한다."""

    AGENTS = "Agents, sessions, and worktrees"
    AUTH = "Authentication and providers"
    ENTERPRISE = "Enterprise and managed settings"
    GIT = "Git and attribution"
    GLOBAL_CONFIG = "Global config settings"
    HOOKS = "Hooks and automation"
    INTERFACE = "Interface and terminal"
    MCP = "MCP"
    MEMORY = "Memory and context"
    MODEL = "Model and responses"
    PERMISSIONS = "Permission settings"
    PLUGINS = "Plugins and skills"
    PRIVACY = "Privacy and telemetry"
    REMOTE = "Remote, desktop, and notifications"
    SANDBOX = "Sandbox settings"
    TOOLS = "Tools"
    UPDATES = "Updates and versioning"

    def __str__(self) -> str:
        return self.value


class Precedence(str, Enum):
    """설정 키 ↔ env 변수 겹침에서 어느 쪽이 이기는지(overlaps.json 의 precedence 값)."""

    ENV = ENV_KEY
    SETTING = "setting"
    RELATED = "related"   # 우선순위를 문서에서 확정하지 못함

    def __str__(self) -> str:
        return self.value
