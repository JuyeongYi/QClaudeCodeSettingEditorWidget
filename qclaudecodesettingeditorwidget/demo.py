"""위젯 테스트용 메인윈도우.

- 중앙: QClaudeCodeSettingEditorWidget
- 하단: [언어 선택]  [확인] → 설정된 키만 담긴 JSON 을 대화상자로 표시,  [취소] → 닫기
실행: python -m qclaudecodesettingeditorwidget [settings.json]
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from . import i18n
from .categories import Category
from .constants import MUTED, Scope
from .i18n import tr
from .widget import QClaudeCodeSettingEditorWidget


SCOPE_CHOICES = [Scope.USER, Scope.PROJECT, Scope.LOCAL, Scope.MANAGED, Scope.ANY_FILE]


def scope_choice_label(scope: Scope) -> str:
    return {
        Scope.USER: tr("User (~/.claude/settings.json)"),
        Scope.PROJECT: tr("Project (.claude/settings.json)"),
        Scope.LOCAL: tr("Local (.claude/settings.local.json)"),
        Scope.MANAGED: tr("Managed settings"),
        Scope.ANY_FILE: tr("All files"),
    }[scope]


class JsonResultDialog(QtWidgets.QDialog):
    """확인 시 뜨는 결과 창: 읽기 전용 JSON + 복사/JSONL 복사."""

    def __init__(self, widget: QClaudeCodeSettingEditorWidget, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(tr("Configured settings (GetSetting)"))
        self.resize(720, 560)
        info = QtWidgets.QLabel(tr("{n} keys are set (checked items only).", n=len(widget.settings())))
        text = QtWidgets.QPlainTextEdit(widget.GetSetting())
        text.setReadOnly(True)
        text.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont))
        copy_json = QtWidgets.QPushButton(tr("Copy JSON"))
        copy_json.clicked.connect(lambda: QtWidgets.QApplication.clipboard().setText(widget.GetSetting()))
        copy_jsonl = QtWidgets.QPushButton(tr("Copy JSONL (one line)"))
        copy_jsonl.clicked.connect(lambda: QtWidgets.QApplication.clipboard().setText(widget.GetSettingJsonl()))
        close = QtWidgets.QPushButton(tr("Close"))
        close.setDefault(True)
        close.clicked.connect(self.accept)
        btns = QtWidgets.QHBoxLayout()
        btns.addWidget(copy_json)
        btns.addWidget(copy_jsonl)
        btns.addStretch(1)
        btns.addWidget(close)
        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(info)
        lay.addWidget(text, 1)
        lay.addLayout(btns)


class DemoMainWindow(QtWidgets.QMainWindow):
    def __init__(self, path: str | Path | None = None, language: str | None = None,
                 categories: Category = Category.ALL, scope: Scope = Scope.USER, version: str | None = None):
        super().__init__()
        self.resize(1200, 800)
        self.editor = QClaudeCodeSettingEditorWidget(language=language, categories=categories,
                                                     targetScope=scope, targetVersion=version)
        self.editor.fileLoaded.connect(self._set_title_path)
        self.editor.fileSaved.connect(self._set_title_path)
        self.editor.settingChanged.connect(self._retranslate)
        self.editor.languageChanged.connect(self._on_language_changed)

        self._lang_label = QtWidgets.QLabel()
        self._lang_combo = QtWidgets.QComboBox()
        for code in self.editor.availableLanguages():
            self._lang_combo.addItem(f"{i18n.language_name(code)} ({code})", code)
        self._lang_combo.setCurrentIndex(max(self._lang_combo.findData(self.editor.language()), 0))
        self._lang_combo.currentIndexChanged.connect(lambda i: self.editor.setLanguage(self._lang_combo.itemData(i)))

        self._scope_label = QtWidgets.QLabel()
        self._scope_combo = QtWidgets.QComboBox()
        for s in SCOPE_CHOICES:
            self._scope_combo.addItem("", int(s))
        self._scope_combo.setCurrentIndex(max(self._scope_combo.findData(int(scope)), 0))
        self._scope_combo.currentIndexChanged.connect(
            lambda i: self.editor.setTargetScope(Scope(self._scope_combo.itemData(i))))
        self._version_label = QtWidgets.QLabel()
        self._version = QtWidgets.QLineEdit(version or "")
        self._version.setMaximumWidth(110)
        self._version.editingFinished.connect(self._apply_version)

        self._ok = QtWidgets.QPushButton()
        self._ok.setDefault(True)
        self._ok.setMinimumWidth(100)
        self._ok.clicked.connect(self.showResult)
        self._cancel = QtWidgets.QPushButton()
        self._cancel.setMinimumWidth(100)
        self._cancel.clicked.connect(self.close)
        self._hint = QtWidgets.QLabel()
        self._hint.setStyleSheet(MUTED)

        bottom = QtWidgets.QHBoxLayout()
        bottom.addWidget(self._lang_label)
        bottom.addWidget(self._lang_combo)
        bottom.addSpacing(12)
        bottom.addWidget(self._scope_label)
        bottom.addWidget(self._scope_combo)
        bottom.addSpacing(12)
        bottom.addWidget(self._version_label)
        bottom.addWidget(self._version)
        bottom.addSpacing(12)
        bottom.addWidget(self._hint, 1)
        bottom.addWidget(self._ok)
        bottom.addWidget(self._cancel)

        central = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(central)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addWidget(self.editor, 1)
        lay.addLayout(bottom)
        self.setCentralWidget(central)

        shortcut = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Return"), self)
        shortcut.activated.connect(self.showResult)
        self._path_title = ""
        self._retranslate()
        if path:
            p = Path(path)
            if p.exists():
                self.editor.loadFile(p)

    def _apply_version(self) -> None:
        try:
            self.editor.setTargetVersion(self._version.text().strip() or None)
            self._version.setStyleSheet("")
        except ValueError:
            self._version.setStyleSheet("color: #d33;")

    @QtCore.Slot()
    def showResult(self) -> None:
        JsonResultDialog(self.editor, self).exec()

    def _on_language_changed(self, code: str) -> None:
        idx = self._lang_combo.findData(code)
        if idx >= 0 and idx != self._lang_combo.currentIndex():
            self._lang_combo.blockSignals(True)
            self._lang_combo.setCurrentIndex(idx)
            self._lang_combo.blockSignals(False)
        self._retranslate()

    def _set_title_path(self, path: str) -> None:
        self._path_title = path
        self._retranslate()

    def _retranslate(self) -> None:
        title = tr("QClaudeCodeSettingEditorWidget — test")
        self.setWindowTitle(f"{title} — {self._path_title}" if self._path_title else title)
        self._lang_label.setText(tr("Language:"))
        self._scope_label.setText(tr("Editing:"))
        for i, s in enumerate(SCOPE_CHOICES):
            self._scope_combo.setItemText(i, scope_choice_label(s))
        self._version_label.setText(tr("Claude Code version:"))
        self._version.setPlaceholderText(tr("all ({version})", version=self.editor.latestVersion()))
        self._ok.setText(tr("OK"))
        self._cancel.setText(tr("Cancel"))
        self._hint.setText(tr("{n} keys set — press OK (Ctrl+Enter) to show the JSON", n=len(self.editor.settings())))


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="python -m qclaudecodesettingeditorwidget")
    ap.add_argument("path", nargs="?", help="settings.json 경로")
    ap.add_argument("--lang", help="언어 코드 (예: ko, en)")
    ap.add_argument("--categories", help="노출할 카테고리 플래그, 예: MODEL|HOOKS|ENV (기본 ALL)")
    ap.add_argument("--exclude", help="제외할 카테고리 플래그, 예: JSON|ADMIN")
    ap.add_argument("--scope", default="USER", help="편집 대상 파일 스코프, 예: USER, PROJECT, MANAGED, ANY_FILE (기본 USER)")
    ap.add_argument("--target-version", help="대상 Claude Code 버전, 예: 2.1.250 (그 버전에 없는 키를 숨김)")
    args = ap.parse_args(sys.argv[1:] if argv is None else argv[1:])
    mask = Category.parse(args.categories) if args.categories else Category.ALL
    if args.exclude:
        mask &= ~Category.parse(args.exclude)
    app = QtWidgets.QApplication(sys.argv)
    win = DemoMainWindow(args.path, args.lang, mask, Scope.parse(args.scope), args.target_version)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
