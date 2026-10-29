"""현지화 — Qt 표준(QTranslator / .ts / .qm) 기반.

소스 문자열은 영어. 언어 파일은 `qccse_<lang>.qm`(lrelease 컴파일) 또는 `qccse_<lang>.ts`(Qt Linguist XML).
.qm 이 없으면 .ts 를 직접 읽는 TsTranslator 로 로드하므로 파일 하나만 두면 그 언어를 쓸 수 있다.

컨텍스트
- "qccse"  : UI 문자열. 코드에서 tr("Open…") 처럼 영어 원문을 소스로 쓴다.
- "schema" : 스키마 설명. 소스는 설정 경로("permissions.allow", "hooks.PreToolUse[].matcher", "env.API_TIMEOUT_MS"),
             번역이 없으면 스키마의 영어 description 을 그대로 쓴다.

검색 디렉터리(뒤가 우선): 패키지 locales/ → 환경변수 QCCSE_LOCALE_DIR(os.pathsep 구분) → add_locale_dir().
언어 파일은 .ts/.qm 을 tools/build_translations.py 로 생성·갱신·컴파일한다.
"""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from PySide6 import QtCore

from .constants import CONTEXT_SCHEMA, CONTEXT_UI, ENV_LANG, ENV_LOCALE_DIR, LOCALE_DIR, LOCALE_FILE_PREFIX, SOURCE_LANG

PACKAGE_LOCALE_DIR = Path(__file__).resolve().parent / LOCALE_DIR

_extra_dirs: list[Path] = []
_current: str | None = None
_installed: list[QtCore.QTranslator] = []


# --------------------------------------------------------------------------- .ts 직접 로딩
class TsTranslator(QtCore.QTranslator):
    """Qt Linguist .ts(XML) 파일을 컴파일 없이 읽는 QTranslator."""

    def __init__(self, path: str | Path, parent: QtCore.QObject | None = None):
        super().__init__(parent)
        self.path = Path(path)
        self._map: dict[tuple[str, str], str] = {}
        self._parse()

    def _parse(self) -> None:
        try:
            root = ET.parse(self.path).getroot()
        except (OSError, ET.ParseError):
            return
        for ctx in root.findall("context"):
            name = (ctx.findtext("name") or "").strip()
            for msg in ctx.findall("message"):
                src = msg.findtext("source")
                trans_el = msg.find("translation")
                if src is None or trans_el is None:
                    continue
                if trans_el.get("type") in ("unfinished", "vanished", "obsolete") and not (trans_el.text or "").strip():
                    continue
                text = trans_el.text or ""
                if text:
                    self._map[(name, src)] = text

    def translate(self, context: str, sourceText: str, disambiguation: str | None = None, n: int = -1) -> str:  # noqa: N803
        # 빈 문자열을 돌려주면 Qt 가 "찾음"으로 간주할 수 있으므로 tr()/describe() 쪽에서도 빈 결과를 원문으로 되돌린다.
        return self._map.get((context, sourceText), "")

    def isEmpty(self) -> bool:  # noqa: N802  (빈 것으로 판정되면 installTranslator 가 거부한다)
        return False

    def __len__(self) -> int:
        return len(self._map)


# --------------------------------------------------------------------------- 디렉터리
def add_locale_dir(path: str | Path) -> None:
    """추가 로케일 디렉터리 등록(가장 높은 우선순위)."""
    p = Path(path)
    if p not in _extra_dirs:
        _extra_dirs.append(p)


def locale_dirs() -> list[Path]:
    dirs = [PACKAGE_LOCALE_DIR]
    for raw in os.environ.get(ENV_LOCALE_DIR, "").split(os.pathsep):
        if raw.strip():
            dirs.append(Path(raw.strip()))
    dirs.extend(_extra_dirs)
    return dirs


def language_files(lang: str) -> list[Path]:
    """lang 의 번역 파일들(디렉터리 우선순위 순). 같은 디렉터리에 .qm 과 .ts 가 있으면 .qm."""
    out: list[Path] = []
    for d in locale_dirs():
        qm = d / f"{LOCALE_FILE_PREFIX}{lang}.qm"
        ts = d / f"{LOCALE_FILE_PREFIX}{lang}.ts"
        if qm.is_file():
            out.append(qm)
        elif ts.is_file():
            out.append(ts)
    return out


def available_languages() -> list[str]:
    langs = {SOURCE_LANG}
    for d in locale_dirs():
        if d.is_dir():
            for f in list(d.glob(f"{LOCALE_FILE_PREFIX}*.qm")) + list(d.glob(f"{LOCALE_FILE_PREFIX}*.ts")):
                langs.add(f.stem[len(LOCALE_FILE_PREFIX):])
    return sorted(langs)


def language_name(lang: str) -> str:
    """언어 표시 이름: 번역 파일의 "_name" 항목(qccse 컨텍스트) → QLocale 네이티브 이름 → 코드."""
    for f in reversed(language_files(lang)):
        t = _make_translator(f)
        if t is not None:
            name = t.translate(CONTEXT_UI, "_name")
            if name:
                return name
    if lang == SOURCE_LANG:
        return "English"
    native = QtCore.QLocale(lang).nativeLanguageName()
    return native or lang


# --------------------------------------------------------------------------- 언어 선택·설치
def _make_translator(path: Path) -> QtCore.QTranslator | None:
    if path.suffix == ".qm":
        t = QtCore.QTranslator()
        return t if t.load(str(path)) else None
    t = TsTranslator(path)
    return t if len(t) else None


def detect_language() -> str:
    """QCCSE_LANG → 시스템 로케일(ko_KR → ko) → en."""
    langs = available_languages()
    forced = os.environ.get(ENV_LANG, "").strip()
    if forced:
        return forced
    name = QtCore.QLocale.system().name()  # 예: ko_KR
    for cand in (name, name.split("_")[0] if name else ""):
        if cand and cand in langs:
            return cand
    return SOURCE_LANG


def set_language(lang: str | None) -> str:
    """번역기를 QCoreApplication 에 설치한다. None 이면 자동 감지. 적용된 언어 코드를 돌려준다."""
    global _current
    lang = lang or detect_language()
    app = QtCore.QCoreApplication.instance()
    if app is not None:
        for t in _installed:
            app.removeTranslator(t)
    _installed.clear()
    if lang != SOURCE_LANG:
        for f in language_files(lang):  # 나중 디렉터리가 우선하도록 순서대로 설치(Qt 는 최근 설치를 먼저 조회)
            t = _make_translator(f)
            if t is not None:
                _installed.append(t)
                if app is not None:
                    app.installTranslator(t)
    _current = lang
    return lang


def current_language() -> str:
    if _current is None:
        set_language(None)
    return _current  # type: ignore[return-value]


# --------------------------------------------------------------------------- 조회
class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def tr(text: str, **kwargs: Any) -> str:
    """UI 문자열 번역(컨텍스트 "qccse"). 번역이 없으면 영어 원문. {name} 자리표시자는 kwargs 로 채운다."""
    current_language()
    out = QtCore.QCoreApplication.translate(CONTEXT_UI, text) or text
    return out.format_map(_SafeDict(kwargs)) if kwargs else out


def describe(path: str, default: str) -> str:
    """설명 번역(컨텍스트 "schema", 소스 = 경로). 없으면 default(영어 원문)."""
    current_language()
    out = QtCore.QCoreApplication.translate(CONTEXT_SCHEMA, path)
    return default if not out or out == path else out


def join_path(parent: str, child: str) -> str:
    return f"{parent}.{child}" if parent else child
