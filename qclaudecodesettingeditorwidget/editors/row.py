"""PropertyRow: 객체 속성 한 줄 — [포함 체크] key (type) [편집기] 설명 + 검증 문제 표시."""
from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtWidgets

from ..constants import ERROR_COLOR, MUTED, MUTED_COLOR, WARNING_COLOR, Precedence, Severity
from ..i18n import describe, tr
from ..keys import setting_info
from ..schema import JsonSchema, first_sentence, schema_types
from ..validation import Issue
from .badges import info_badges
from .base import BaseEditor
from .slot import ValueSlot

MAX_SHOWN_ISSUES = 5


def precedence_label(precedence: str) -> str:
    """설정 키 ↔ env 변수 겹침의 우선순위 표시 문자열."""
    labels: dict[str, str] = {Precedence.ENV: tr("env wins"), Precedence.SETTING: tr("setting wins")}
    return labels.get(precedence, tr("related"))


def _type_badge(schema: JsonSchema) -> str:
    types = schema_types(schema)
    if not types and ("anyOf" in schema or "oneOf" in schema):
        return "anyOf"
    return "/".join(types) if types else ""


class PropertyRow(QtWidgets.QWidget):
    """객체의 속성 한 줄: [포함 체크] key  (type)  [편집기]  설명.

    값은 ValueSlot 을 거쳐 들어가므로 폼이 담을 수 없는 값도 그대로 보존된다. editor 는 폼 편집기 자체다.
    required 키는 체크를 끌 수 없지만, 로드한 값에 빠져 있으면 빠진 그대로 보존(체크 해제·검증이 알림)한다.
    """

    changed = QtCore.Signal()
    envLinkActivated = QtCore.Signal(str)  # 겹치는 env 변수 링크 클릭

    def __init__(self, key: str, schema: JsonSchema, root: JsonSchema, depth: int,
                 required: bool = False, parent: QtWidgets.QWidget | None = None, path: str = "",
                 related: list[dict[str, str]] | None = None):
        super().__init__(parent)
        from . import create_editor  # 순환 임포트 회피

        self.key = key
        self.schema = schema
        self.required = required
        self.path = path or key
        self.related: list[dict[str, str]] = list(related or [])  # [{"env", "precedence", "note"}]
        self.info = setting_info(self.path)  # 스코프·버전 메타데이터(keys.py). 모르는 경로면 None
        self._loading = 0
        self._issue_label: QtWidgets.QLabel | None = None
        self.description = describe(self.path, schema.get("description", ""))

        self.check = QtWidgets.QCheckBox()
        self.check.setToolTip(tr("Check to include this key in the settings JSON"))
        if required:
            self.check.setChecked(True)
            self.check.setEnabled(False)
            self.check.setToolTip(tr("Required key"))
        self.check.toggled.connect(self._on_toggle)

        self.name_label = QtWidgets.QLabel(key)
        f = self.name_label.font()
        f.setBold(True)
        self.name_label.setFont(f)
        self.name_label.setToolTip(self.description or key)

        badge = QtWidgets.QLabel(_type_badge(schema))
        badge.setStyleSheet(MUTED + " font-size: 90%;")

        self.editor: BaseEditor = create_editor(schema, root, depth + 1, key=key, path=self.path)
        self.slot = ValueSlot(self.editor)
        self.slot.changed.connect(self._on_editor_changed)

        head = QtWidgets.QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.addWidget(self.check)
        head.addWidget(self.name_label)
        head.addWidget(badge)
        for info_badge in info_badges(self.info):
            head.addWidget(info_badge)
        head.addSpacing(8)
        if self.slot.compact:
            head.addWidget(self.slot, 1)
        else:
            head.addStretch(1)

        self._lay = QtWidgets.QVBoxLayout(self)
        self._lay.setContentsMargins(0, 4, 0, 4)
        self._lay.setSpacing(2)
        self._lay.addLayout(head)
        if self.description:
            self.desc_label = QtWidgets.QLabel(first_sentence(self.description))
            self.desc_label.setWordWrap(True)
            self.desc_label.setToolTip(self.description)
            self.desc_label.setStyleSheet(MUTED + " font-size: 90%; margin-left: 22px;")
            self.desc_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
            self._lay.addWidget(self.desc_label)
        if self.related:
            self.related_label = QtWidgets.QLabel(self._related_html())
            self.related_label.setStyleSheet("font-size: 90%; margin-left: 22px;")
            self.related_label.setTextFormat(QtCore.Qt.TextFormat.RichText)
            self.related_label.setOpenExternalLinks(False)
            self.related_label.setWordWrap(True)
            self.related_label.setToolTip("\n\n".join(
                f"{r['env']} ({precedence_label(r.get('precedence', Precedence.RELATED))})\n{r.get('note', '')}".strip()
                for r in self.related))
            self.related_label.linkActivated.connect(self.envLinkActivated)
            self._lay.addWidget(self.related_label)
        if not self.slot.compact:
            body = QtWidgets.QHBoxLayout()
            body.setContentsMargins(22, 0, 0, 0)
            body.addWidget(self.slot, 1)
            self._lay.addLayout(body)
        self._sync_enabled()

    # ---- state
    def included(self) -> bool:
        return self.check.isChecked()

    def setIncluded(self, on: bool, *, force: bool = False) -> None:
        """포함 여부. required 키는 force=True(로드한 값에 빠져 있을 때)일 때만 끌 수 있다."""
        if self.required and not force:
            return
        self.check.setChecked(on)
        if self.required:
            self.check.setEnabled(not on)  # 빠진 required 키는 사용자가 다시 켤 수 있게

    def setValue(self, value: Any) -> None:
        self._loading += 1
        try:
            self.slot.setValue(value)
            self.setIncluded(True, force=True)
        finally:
            self._loading -= 1

    def value(self) -> Any:
        return self.slot.value()

    def resetValue(self) -> None:
        """편집기를 기본값으로(raw 보존 상태도 해제). 포함 여부는 바꾸지 않는다."""
        self.slot.reset()

    def setIssues(self, issues: list[Issue]) -> None:
        """이 키(하위 경로 포함)의 검증 문제를 행 아래에 표시. 빈 목록이면 숨긴다."""
        if not issues:
            if self._issue_label is not None:
                self._issue_label.hide()
            return
        if self._issue_label is None:
            self._issue_label = QtWidgets.QLabel()
            self._issue_label.setWordWrap(True)
            self._issue_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
            self._lay.insertWidget(1, self._issue_label)
        color = ERROR_COLOR if any(i.severity is Severity.ERROR for i in issues) else WARNING_COLOR
        lines = [f"⚠ {self._relative(i)}" for i in issues[:MAX_SHOWN_ISSUES]]
        if len(issues) > MAX_SHOWN_ISSUES:
            lines.append(tr("…and {n} more", n=len(issues) - MAX_SHOWN_ISSUES))
        self._issue_label.setText("\n".join(lines))
        self._issue_label.setStyleSheet(f"color: {color}; font-size: 90%; margin-left: 22px;")
        self._issue_label.show()

    def _relative(self, issue: Issue) -> str:
        rest = issue.path[len(self.path):].lstrip(".") if issue.path.startswith(self.path) else issue.path
        return f"{rest}: {issue.message}" if rest else issue.message

    def matches(self, text: str) -> bool:
        t = text.lower()
        return (t in self.key.lower() or t in self.description.lower()
                or t in self.schema.get("description", "").lower()
                or any(t in r["env"].lower() for r in self.related))

    def _related_html(self) -> str:
        links = ", ".join(
            f'<a href="{r["env"]}">{r["env"]}</a> <span style="color:{MUTED_COLOR}">'
            f'({precedence_label(r.get("precedence", Precedence.RELATED))})</span>'
            for r in self.related)
        return f'<span style="color:{MUTED_COLOR}">{tr("Related env:")}</span> {links}'

    # ---- internals
    def _sync_enabled(self) -> None:
        self.slot.setEnabled(self.check.isChecked())

    def _on_toggle(self, on: bool) -> None:
        self._sync_enabled()
        if self.required and on:
            self.check.setEnabled(False)
        if not self._loading:
            self.changed.emit()

    def _on_editor_changed(self) -> None:
        if self._loading:
            return
        if not self.check.isChecked():
            self.check.setChecked(True)  # 편집하면 자동 포함(toggled → changed 발생)
            return
        self.changed.emit()
