"""SettingInfo → 행 머리의 배지(스코프·since·deprecated·removed)."""
from __future__ import annotations

from PySide6 import QtWidgets

from ..constants import Scope
from ..i18n import tr
from ..spec import SettingInfo

_STYLE = "color: {c}; font-size: 85%; border: 1px solid {c}; border-radius: 3px; padding: 0 3px;"
SCOPE_COLOR = "#d08a00"
SINCE_COLOR = "#3a7bd5"
LIFECYCLE_COLOR = "#c0392b"


def scope_label(scope: Scope) -> str:
    """Scope 비트 → 'user · managed' 같은 짧은 라벨."""
    names = {Scope.USER: tr("user"), Scope.PROJECT: tr("project"), Scope.LOCAL: tr("local"),
             Scope.MANAGED: tr("managed"), Scope.GLOBAL_CONFIG: tr("global config")}
    return " · ".join(v for k, v in names.items() if k & scope)


def scope_files(scope: Scope) -> str:
    """Scope 비트 → 실제 파일 목록(툴팁용)."""
    files = {Scope.USER: "~/.claude/settings.json", Scope.PROJECT: ".claude/settings.json",
             Scope.LOCAL: ".claude/settings.local.json", Scope.MANAGED: tr("managed settings"),
             Scope.GLOBAL_CONFIG: "~/.claude.json"}
    return ", ".join(v for k, v in files.items() if k & scope)


def _badge(text: str, tip: str, color: str) -> QtWidgets.QLabel:
    label = QtWidgets.QLabel(text)
    label.setToolTip(tip)
    label.setStyleSheet(_STYLE.format(c=color))
    return label


def info_badges(info: SettingInfo | None) -> list[QtWidgets.QLabel]:
    """문서 기준의 고정 사실만 표시한다(편집 대상 스코프·버전에 따른 숨김은 위젯 필터가 한다)."""
    if info is None:
        return []
    out = []
    if info.scope != Scope.ANY_FILE:
        out.append(_badge(scope_label(info.scope), tr("Only honored in: {files}", files=scope_files(info.scope)),
                          SCOPE_COLOR))
    if info.since:
        out.append(_badge(f"v{info.since}+", tr("Requires Claude Code v{version} or later", version=info.since),
                          SINCE_COLOR))
    if info.removed:
        out.append(_badge(tr("removed v{version}", version=info.removed),
                          tr("Removed in Claude Code v{version}; it has no effect on that version or later",
                             version=info.removed), LIFECYCLE_COLOR))
    elif info.deprecated:
        tip = (tr("Deprecated since Claude Code v{version}", version=info.deprecated_since)
               if info.deprecated_since else tr("Deprecated"))
        if info.replaced_by:
            tip += "\n" + tr("Use {key} instead", key=info.replaced_by.key)
        out.append(_badge(tr("deprecated"), tip, LIFECYCLE_COLOR))
    return out
