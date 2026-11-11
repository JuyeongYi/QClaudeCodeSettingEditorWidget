"""위젯 툴바 부품: 편집 대상 파일(스코프) 선택 콤보, 숨긴 키 수 표시, 검증 문제 버튼."""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from .constants import ERROR_COLOR, MUTED, WARNING_COLOR, Scope, Severity
from .i18n import tr
from .validation import Issue

SCOPE_CHOICES = [Scope.USER, Scope.PROJECT, Scope.LOCAL, Scope.MANAGED, Scope.ANY_FILE]
SINGLE_SCOPES = [Scope.USER, Scope.PROJECT, Scope.LOCAL, Scope.MANAGED]
MAX_MENU_ISSUES = 40
MAX_TOOLTIP_KEYS = 30


def scope_choice_label(scope: Scope) -> str:
    """편집 대상 선택지 표시 이름. SCOPE_CHOICES 밖의 조합은 플래그 이름을 잇는다."""
    labels = {
        Scope.USER: tr("User (~/.claude/settings.json)"),
        Scope.PROJECT: tr("Project (.claude/settings.json)"),
        Scope.LOCAL: tr("Local (.claude/settings.local.json)"),
        Scope.MANAGED: tr("Managed settings"),
        Scope.ANY_FILE: tr("All files"),
    }
    return labels.get(scope) or " | ".join(s.name or "" for s in SINGLE_SCOPES if s & scope)


class ScopeSelector(QtWidgets.QWidget):
    """「편집 대상:」 라벨 + 스코프 콤보. 고르면 scopeChanged(Scope)."""

    scopeChanged = QtCore.Signal(object)

    def __init__(self, scope: Scope, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self._combo = QtWidgets.QComboBox()
        self._combo.setToolTip(tr("Settings file being edited. Keys that have no effect in it are hidden."))
        for s in SCOPE_CHOICES:
            self._combo.addItem(scope_choice_label(s), int(s))
        self.setScope(scope)
        self._combo.currentIndexChanged.connect(lambda i: self.scopeChanged.emit(Scope(self._combo.itemData(i))))
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(QtWidgets.QLabel(tr("Editing:")))
        lay.addWidget(self._combo)

    def scope(self) -> Scope:
        return Scope(self._combo.currentData())

    def setScope(self, scope: Scope) -> None:
        """시그널 없이 콤보를 맞춘다. 선택지 밖 조합(USER|PROJECT 등)은 항목을 더해 보여 준다."""
        idx = self._combo.findData(int(scope))
        if idx < 0:
            self._combo.addItem(scope_choice_label(scope), int(scope))
            idx = self._combo.count() - 1
        self._combo.blockSignals(True)
        self._combo.setCurrentIndex(idx)
        self._combo.blockSignals(False)


class HiddenKeysLabel(QtWidgets.QLabel):
    """대상 스코프·버전에서 효력이 없어 숨긴 키 수. 없으면 숨는다."""

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setStyleSheet(MUTED)
        self.hide()

    def setKeys(self, hidden: list[str], with_values: list[str]) -> None:  # noqa: N802
        if not hidden:
            self.hide()
            return
        self.setText(tr("{n} hidden", n=len(hidden)))
        tip = tr("{n} keys have no effect in the selected file or Claude Code version and are hidden. "
                 "Pick “All files” to show them.", n=len(hidden))
        if with_values:
            shown = ", ".join(with_values[:MAX_TOOLTIP_KEYS]) + (" …" if len(with_values) > MAX_TOOLTIP_KEYS else "")
            tip += "\n" + tr("Hidden keys that have values (kept as is): {keys}", keys=shown)
        self.setToolTip(tip)
        self.show()


class IssuesButton(QtWidgets.QToolButton):
    """「⚠ n problems」 버튼. 누르면 문제 목록 메뉴, 고르면 issueActivated(Issue). 문제가 없으면 숨는다."""

    issueActivated = QtCore.Signal(object)

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self._issues: list[Issue] = []
        self._menu = QtWidgets.QMenu(self)
        self._menu.aboutToShow.connect(self._fill_menu)
        self.setMenu(self._menu)
        self.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setAutoRaise(True)
        self.hide()

    def issues(self) -> list[Issue]:
        return list(self._issues)

    def setIssues(self, issues: list[Issue]) -> None:  # noqa: N802
        self._issues = list(issues)
        if not issues:
            self.hide()
            return
        n_err = sum(1 for i in issues if i.severity is Severity.ERROR)
        color = ERROR_COLOR if n_err else WARNING_COLOR
        self.setText(tr("⚠ {n} problems", n=len(issues)))
        self.setStyleSheet(f"QToolButton {{ color: {color}; font-weight: bold; }}")
        self.setToolTip(tr("{errors} errors, {warnings} warnings — they do not block editing or saving. "
                           "Click to jump to one.", errors=n_err, warnings=len(issues) - n_err))
        self.show()

    def _fill_menu(self) -> None:
        self._menu.clear()
        for issue in self._issues[:MAX_MENU_ISSUES]:
            mark = "✖" if issue.severity is Severity.ERROR else "⚠"
            action = self._menu.addAction(f"{mark} {issue}")
            action.triggered.connect(lambda _=False, i=issue: self.issueActivated.emit(i))
        if len(self._issues) > MAX_MENU_ISSUES:
            more = self._menu.addAction(tr("…and {n} more", n=len(self._issues) - MAX_MENU_ISSUES))
            more.setEnabled(False)
