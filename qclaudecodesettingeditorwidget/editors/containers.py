"""컨테이너 편집기: object / array / dict(additionalProperties) / anyOf / nullable / raw JSON."""
from __future__ import annotations

import json
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from ..constants import INVALID_STYLE, MUTED, MUTED_COLOR, Precedence
from ..i18n import describe, join_path, tr
from ..keys import setting_info
from ..schema import (
    JsonSchema,
    default_for,
    first_sentence,
    resolve_ref,
    schema_types,
    value_matches,
    variant_label,
)
from .badges import info_badges
from .base import BaseEditor

FRAME_STYLE = "QFrame#nested { border-left: 2px solid palette(mid); }"


def precedence_label(precedence: str) -> str:
    labels: dict[str, str] = {Precedence.ENV: tr("env wins"), Precedence.SETTING: tr("setting wins")}
    return labels.get(precedence, tr("related"))


def _type_badge(schema: JsonSchema) -> str:
    types = schema_types(schema)
    if not types and ("anyOf" in schema or "oneOf" in schema):
        return "anyOf"
    return "/".join(types) if types else ""


def _tool_button(text: str, tip: str, slot) -> QtWidgets.QToolButton:
    b = QtWidgets.QToolButton()
    b.setText(text)
    b.setToolTip(tip)
    b.clicked.connect(slot)
    return b


# --------------------------------------------------------------------------- PropertyRow
class PropertyRow(QtWidgets.QWidget):
    """객체의 속성 한 줄: [포함 체크] key  (type)  [편집기]  설명."""

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
        self.editor.changed.connect(self._on_editor_changed)

        head = QtWidgets.QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.addWidget(self.check)
        head.addWidget(self.name_label)
        head.addWidget(badge)
        for info_badge in info_badges(self.info):
            head.addWidget(info_badge)
        head.addSpacing(8)
        if self.editor.compact:
            head.addWidget(self.editor, 1)
        else:
            head.addStretch(1)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(2)
        lay.addLayout(head)
        if self.description:
            self.desc_label = QtWidgets.QLabel(first_sentence(self.description))
            self.desc_label.setWordWrap(True)
            self.desc_label.setToolTip(self.description)
            self.desc_label.setStyleSheet(MUTED + " font-size: 90%; margin-left: 22px;")
            self.desc_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
            lay.addWidget(self.desc_label)
        if self.related:
            self.related_label = QtWidgets.QLabel(self._related_html())
            self.related_label.setStyleSheet("font-size: 90%; margin-left: 22px;")
            self.related_label.setTextFormat(QtCore.Qt.TextFormat.RichText)
            self.related_label.setOpenExternalLinks(False)
            self.related_label.setWordWrap(True)
            self.related_label.setToolTip("\n\n".join(
                f"{r['env']} ({precedence_label(r.get('precedence', 'related'))})\n{r.get('note', '')}".strip()
                for r in self.related))
            self.related_label.linkActivated.connect(self.envLinkActivated)
            lay.addWidget(self.related_label)
        if not self.editor.compact:
            body = QtWidgets.QHBoxLayout()
            body.setContentsMargins(22, 0, 0, 0)
            body.addWidget(self.editor, 1)
            lay.addLayout(body)
        self._sync_enabled()

    # ---- state
    def included(self) -> bool:
        return self.check.isChecked()

    def setIncluded(self, on: bool) -> None:
        if not self.required:
            self.check.setChecked(on)

    def setValue(self, value: Any) -> None:
        self._loading += 1
        try:
            self.editor.setValue(value)
            self.setIncluded(True)
        finally:
            self._loading -= 1

    def value(self) -> Any:
        return self.editor.value()

    def matches(self, text: str) -> bool:
        t = text.lower()
        return (t in self.key.lower() or t in self.description.lower()
                or t in self.schema.get("description", "").lower()
                or any(t in r["env"].lower() for r in self.related))

    def _related_html(self) -> str:
        links = ", ".join(
            f'<a href="{r["env"]}">{r["env"]}</a> <span style="color:{MUTED_COLOR}">({precedence_label(r.get("precedence", Precedence.RELATED))})</span>'
            for r in self.related)
        return f'<span style="color:{MUTED_COLOR}">{tr("Related env:")}</span> {links}'

    # ---- internals
    def _sync_enabled(self) -> None:
        self.editor.setEnabled(self.check.isChecked())

    def _on_toggle(self, _on: bool) -> None:
        self._sync_enabled()
        if not self._loading:
            self.changed.emit()

    def _on_editor_changed(self) -> None:
        if self._loading:
            return
        if not self.check.isChecked():
            self.check.setChecked(True)  # 편집하면 자동 포함(toggled → changed 발생)
            return
        self.changed.emit()


# --------------------------------------------------------------------------- ObjectEditor
class ObjectEditor(BaseEditor):
    """properties 기반 객체. additionalProperties 스키마가 있으면 추가 항목용 DictEditor 를 덧붙인다.

    스키마에 없는 키(additionalProperties 가 스키마가 아닐 때)는 _passthrough 에 보존해 다시 내보낸다.
    """

    def __init__(self, schema: JsonSchema, root: JsonSchema, depth: int = 0, parent=None, path: str = ""):
        super().__init__(schema, root, depth, parent, path)
        self.rows: dict[str, PropertyRow] = {}
        self._passthrough: dict[str, Any] = {}
        self._extra: DictEditor | None = None
        required = set(schema.get("required", []))

        frame = QtWidgets.QFrame()
        frame.setObjectName("nested")
        frame.setStyleSheet(FRAME_STYLE)
        inner = QtWidgets.QVBoxLayout(frame)
        inner.setContentsMargins(8, 2, 0, 2)
        inner.setSpacing(0)
        for key, prop in schema.get("properties", {}).items():
            row = PropertyRow(key, resolve_ref(prop, root), root, depth, key in required, path=join_path(path, key))
            row.changed.connect(self._emit)
            self.rows[key] = row
            inner.addWidget(row)
        addl = schema.get("additionalProperties")
        if isinstance(addl, dict):
            title = QtWidgets.QLabel(tr("Additional entries"))
            title.setStyleSheet(MUTED + " font-size: 90%;")
            inner.addWidget(title)
            self._extra = DictEditor(schema, root, depth + 1, path=path)
            self._extra.changed.connect(self._emit)
            inner.addWidget(self._extra)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(frame)

    def value(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, row in self.rows.items():
            if row.included():
                out[key] = row.value()
        if self._extra is not None:
            for k, v in self._extra.value().items():
                out.setdefault(k, v)
        for k, v in self._passthrough.items():
            out.setdefault(k, v)
        return out

    def setValue(self, value: Any) -> None:
        data = value if isinstance(value, dict) else {}
        with self.loading():
            extras: dict[str, Any] = {}
            for k, v in data.items():
                if k in self.rows:
                    self.rows[k].setValue(v)
                else:
                    extras[k] = v
            for k, row in self.rows.items():
                if k not in data:
                    row.setIncluded(False)
                    row.editor.reset()
            if self._extra is not None:
                self._extra.setValue(extras)
                self._passthrough = {}
            else:
                self._passthrough = extras


# --------------------------------------------------------------------------- DictEditor
class DictEditor(BaseEditor):
    """additionalProperties 스키마를 값으로 갖는 자유 키 맵."""

    def __init__(self, schema: JsonSchema, root: JsonSchema, depth: int = 0, parent=None, path: str = ""):
        super().__init__(schema, root, depth, parent, path)
        addl = schema.get("additionalProperties")
        self._value_schema: JsonSchema = resolve_ref(addl, root) if isinstance(addl, dict) else {}
        self._key_pattern: QtCore.QRegularExpression | None = None
        pn = schema.get("propertyNames", {})
        if isinstance(pn, dict) and isinstance(pn.get("pattern"), str):
            rx = QtCore.QRegularExpression(pn["pattern"])
            if rx.isValid():
                self._key_pattern = rx
        self._rows: list[tuple[QtWidgets.QWidget, QtWidgets.QLineEdit, BaseEditor]] = []

        self._list = QtWidgets.QVBoxLayout()
        self._list.setContentsMargins(0, 0, 0, 0)
        self._list.setSpacing(2)
        add = QtWidgets.QPushButton(tr("+ Add item"))
        add.setFlat(True)
        add.clicked.connect(lambda: self._add_row("", default_for(self._value_schema, root), focus=True))
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(self._list)
        lay.addWidget(add, 0, QtCore.Qt.AlignmentFlag.AlignLeft)

    def _add_row(self, key: str, value: Any, focus: bool = False) -> None:
        from . import create_editor

        wrap = QtWidgets.QWidget()
        h = QtWidgets.QHBoxLayout(wrap)
        h.setContentsMargins(0, 0, 0, 0)
        key_edit = QtWidgets.QLineEdit(key)
        key_edit.setPlaceholderText(tr("key"))
        key_edit.setMinimumWidth(140)
        key_edit.setMaximumWidth(260)
        key_edit.textChanged.connect(lambda: self._validate_key(key_edit))
        key_edit.textChanged.connect(self._emit)
        editor = create_editor(self._value_schema, self.root, self.level + 1, path=join_path(self.path, "*"))
        editor.setValue(value)
        editor.changed.connect(self._emit)
        entry = (wrap, key_edit, editor)
        rm = _tool_button("✕", tr("Remove"), lambda: self._remove_row(entry))
        h.addWidget(key_edit)
        h.addWidget(QtWidgets.QLabel(":"))
        h.addWidget(editor, 1)
        h.addWidget(rm, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        self._rows.append(entry)
        self._list.addWidget(wrap)
        self._validate_key(key_edit)
        if focus:
            key_edit.setFocus()
            self._emit()

    def _remove_row(self, entry: tuple) -> None:
        if entry in self._rows:
            self._rows.remove(entry)
            entry[0].setParent(None)
            entry[0].deleteLater()
            self._emit()

    def _validate_key(self, key_edit: QtWidgets.QLineEdit) -> None:
        text = key_edit.text()
        ok = bool(text) and (self._key_pattern is None or self._key_pattern.match(text).hasMatch())
        key_edit.setStyleSheet("" if ok or not text else INVALID_STYLE)

    def value(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for _, key_edit, editor in self._rows:
            k = key_edit.text()
            if k:
                out[k] = editor.value()
        return out

    def setValue(self, value: Any) -> None:
        data = value if isinstance(value, dict) else {}
        with self.loading():
            for wrap, _, _ in self._rows:
                wrap.setParent(None)
                wrap.deleteLater()
            self._rows.clear()
            for k, v in data.items():
                self._add_row(k, v)


# --------------------------------------------------------------------------- 배열
class StringListEditor(BaseEditor):
    """문자열 배열: 인라인 편집 리스트 + 추가/삭제/이동."""

    def __init__(self, schema: JsonSchema, root: JsonSchema, depth: int = 0, parent=None, path: str = ""):
        super().__init__(schema, root, depth, parent, path)
        self._list = QtWidgets.QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.setMinimumHeight(60)
        self._list.setMaximumHeight(160)
        self._list.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
        self._list.itemChanged.connect(self._emit)
        items = resolve_ref(schema.get("items", {}), root)
        ex = items.get("examples") or schema.get("examples")
        hint = ""
        if isinstance(ex, list) and ex:
            sample = ex[0] if not isinstance(ex[0], list) else ", ".join(map(str, ex[0]))
            hint = tr("e.g. {value}", value=sample)
        self._list.setToolTip(describe(path + "[]", items.get("description", "")) or hint)

        btns = QtWidgets.QVBoxLayout()
        btns.setContentsMargins(0, 0, 0, 0)
        for text, tip, slot in (("+", tr("Add"), self._add),
                                ("−", tr("Remove"), self._remove),
                                ("▲", tr("Move up"), lambda: self._move(-1)),
                                ("▼", tr("Move down"), lambda: self._move(1))):
            btns.addWidget(_tool_button(text, tip, slot))
        btns.addStretch(1)

        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._list, 1)
        lay.addLayout(btns)

    def _new_item(self, text: str) -> QtWidgets.QListWidgetItem:
        it = QtWidgets.QListWidgetItem(text)
        it.setFlags(it.flags() | QtCore.Qt.ItemFlag.ItemIsEditable)
        return it

    def _add(self) -> None:
        it = self._new_item("")
        self._list.addItem(it)
        self._list.setCurrentItem(it)
        self._list.editItem(it)
        self._emit()

    def _remove(self) -> None:
        row = self._list.currentRow()
        if row >= 0:
            self._list.takeItem(row)
            self._emit()

    def _move(self, delta: int) -> None:
        row = self._list.currentRow()
        new = row + delta
        if row < 0 or not (0 <= new < self._list.count()):
            return
        it = self._list.takeItem(row)
        self._list.insertItem(new, it)
        self._list.setCurrentRow(new)
        self._emit()

    def value(self) -> list[str]:
        return [self._list.item(i).text() for i in range(self._list.count())]

    def setValue(self, value: Any) -> None:
        with self.loading():
            self._list.clear()
            for v in (value if isinstance(value, list) else []):
                self._list.addItem(self._new_item(str(v)))


class CheckListEditor(BaseEditor):
    """enum 문자열 배열: 체크 리스트(enum 순서 유지)."""

    def __init__(self, schema: JsonSchema, root: JsonSchema, depth: int = 0, parent=None, path: str = ""):
        super().__init__(schema, root, depth, parent, path)
        items = resolve_ref(schema.get("items", {}), root)
        self._list = QtWidgets.QListWidget()
        self._list.setMaximumHeight(140)
        for v in items.get("enum", []):
            it = QtWidgets.QListWidgetItem(str(v))
            it.setData(QtCore.Qt.ItemDataRole.UserRole, v)
            it.setFlags(QtCore.Qt.ItemFlag.ItemIsUserCheckable | QtCore.Qt.ItemFlag.ItemIsEnabled)
            it.setCheckState(QtCore.Qt.CheckState.Unchecked)
            self._list.addItem(it)
        self._list.itemChanged.connect(self._emit)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._list)

    def value(self) -> list[Any]:
        return [self._list.item(i).data(QtCore.Qt.ItemDataRole.UserRole)
                for i in range(self._list.count())
                if self._list.item(i).checkState() == QtCore.Qt.CheckState.Checked]

    def setValue(self, value: Any) -> None:
        wanted = set(value) if isinstance(value, list) else set()
        with self.loading():
            for i in range(self._list.count()):
                it = self._list.item(i)
                on = it.data(QtCore.Qt.ItemDataRole.UserRole) in wanted
                it.setCheckState(QtCore.Qt.CheckState.Checked if on else QtCore.Qt.CheckState.Unchecked)


class ListEditor(BaseEditor):
    """임의 항목 배열: 항목마다 자식 편집기 + 이동/삭제."""

    def __init__(self, schema: JsonSchema, root: JsonSchema, depth: int = 0, parent=None, path: str = ""):
        super().__init__(schema, root, depth, parent, path)
        self._item_schema = resolve_ref(schema.get("items", {}), root)
        self._items: list[tuple[QtWidgets.QWidget, BaseEditor, QtWidgets.QLabel]] = []
        self._list = QtWidgets.QVBoxLayout()
        self._list.setContentsMargins(0, 0, 0, 0)
        self._list.setSpacing(4)
        add = QtWidgets.QPushButton(tr("+ Add item"))
        add.setFlat(True)
        add.clicked.connect(lambda: self._add_item(default_for(self._item_schema, root), emit=True))
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(self._list)
        lay.addWidget(add, 0, QtCore.Qt.AlignmentFlag.AlignLeft)

    def _add_item(self, value: Any, emit: bool = False) -> None:
        from . import create_editor

        frame = QtWidgets.QFrame()
        frame.setObjectName("nested")
        frame.setStyleSheet(FRAME_STYLE)
        v = QtWidgets.QVBoxLayout(frame)
        v.setContentsMargins(8, 2, 0, 2)
        head = QtWidgets.QHBoxLayout()
        idx_label = QtWidgets.QLabel()
        idx_label.setStyleSheet(MUTED)
        head.addWidget(idx_label)
        head.addStretch(1)
        editor = create_editor(self._item_schema, self.root, self.level + 1, path=self.path + "[]")
        editor.setValue(value)
        editor.changed.connect(self._emit)
        entry = (frame, editor, idx_label)
        head.addWidget(_tool_button("▲", tr("Move up"), lambda: self._move(entry, -1)))
        head.addWidget(_tool_button("▼", tr("Move down"), lambda: self._move(entry, 1)))
        head.addWidget(_tool_button("✕", tr("Remove"), lambda: self._remove(entry)))
        v.addLayout(head)
        v.addWidget(editor)
        self._items.append(entry)
        self._list.addWidget(frame)
        self._renumber()
        if emit:
            self._emit()

    def _remove(self, entry: tuple) -> None:
        if entry in self._items:
            self._items.remove(entry)
            entry[0].setParent(None)
            entry[0].deleteLater()
            self._renumber()
            self._emit()

    def _move(self, entry: tuple, delta: int) -> None:
        i = self._items.index(entry)
        j = i + delta
        if not (0 <= j < len(self._items)):
            return
        self._items[i], self._items[j] = self._items[j], self._items[i]
        self._list.removeWidget(entry[0])
        self._list.insertWidget(j, entry[0])
        self._renumber()
        self._emit()

    def _renumber(self) -> None:
        for i, (_, _, label) in enumerate(self._items):
            label.setText(f"[{i}]")

    def value(self) -> list[Any]:
        return [editor.value() for _, editor, _ in self._items]

    def setValue(self, value: Any) -> None:
        with self.loading():
            for frame, _, _ in self._items:
                frame.setParent(None)
                frame.deleteLater()
            self._items.clear()
            for v in (value if isinstance(value, list) else []):
                self._add_item(v)


# --------------------------------------------------------------------------- anyOf / nullable / raw
class AnyOfEditor(BaseEditor):
    """anyOf/oneOf: 변형 선택 콤보 + 스택. 값 로드 시 value_matches 로 변형 자동 선택, 실패 시 raw JSON."""

    def __init__(self, variants: list[JsonSchema], schema: JsonSchema, root: JsonSchema, depth: int = 0,
                 parent=None, path: str = ""):
        super().__init__(schema, root, depth, parent, path)
        self._variants = variants
        self._editors: list[BaseEditor | None] = [None] * (len(variants) + 1)
        self._combo = QtWidgets.QComboBox()
        for v in variants:
            self._combo.addItem(variant_label(v))
        self._combo.addItem(tr("(raw JSON)"))
        self._combo.setToolTip(tr("Pick one of the allowed shapes (anyOf)"))
        self._stack = QtWidgets.QStackedWidget()
        for _ in range(len(variants) + 1):
            self._stack.addWidget(QtWidgets.QWidget())  # 자리표시자, 필요 시 실제 편집기로 교체
        self._combo.currentIndexChanged.connect(self._on_select)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        top = QtWidgets.QHBoxLayout()
        top.addWidget(QtWidgets.QLabel(tr("Variant:")))
        top.addWidget(self._combo)
        top.addStretch(1)
        lay.addLayout(top)
        lay.addWidget(self._stack)
        self._ensure_editor(0)

    def _ensure_editor(self, idx: int) -> BaseEditor:
        from . import create_editor

        ed = self._editors[idx]
        if ed is None:
            if idx < len(self._variants):
                ed = create_editor(self._variants[idx], self.root, self.level + 1, path=self.path)
                ed.setValue(default_for(self._variants[idx], self.root))
            else:
                ed = RawJsonEditor(self.schema, self.root, self.level + 1, path=self.path)
                ed.setValue(None)
            ed.changed.connect(self._emit)
            old = self._stack.widget(idx)
            self._stack.removeWidget(old)
            if old is not None:
                old.deleteLater()
            self._stack.insertWidget(idx, ed)
            self._editors[idx] = ed
        return ed

    def _on_select(self, idx: int) -> None:
        self._ensure_editor(idx)
        self._stack.setCurrentIndex(idx)
        self._emit()

    def currentIndex(self) -> int:
        return self._combo.currentIndex()

    def value(self) -> Any:
        return self._ensure_editor(self._combo.currentIndex()).value()

    def setValue(self, value: Any) -> None:
        idx = len(self._variants)  # 기본: raw
        for i, v in enumerate(self._variants):
            if value_matches(v, value, self.root):
                idx = i
                break
        with self.loading():
            ed = self._ensure_editor(idx)
            ed.setValue(value)
            self._combo.setCurrentIndex(idx)
            self._stack.setCurrentIndex(idx)


class NullableEditor(BaseEditor):
    """type: [X, "null"] → [null 체크] + X 편집기."""

    compact = True

    def __init__(self, inner_schema: JsonSchema, schema: JsonSchema, root: JsonSchema, depth: int = 0,
                 parent=None, path: str = ""):
        super().__init__(schema, root, depth, parent, path)
        from . import create_editor

        self._null = QtWidgets.QCheckBox(tr("null"))
        self._inner = create_editor(inner_schema, root, depth + 1, path=path)
        self.compact = self._inner.compact
        self._null.toggled.connect(self._on_null)
        self._inner.changed.connect(self._emit)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._null)
        lay.addWidget(self._inner, 1)

    def _on_null(self, on: bool) -> None:
        self._inner.setEnabled(not on)
        self._emit()

    def value(self) -> Any:
        return None if self._null.isChecked() else self._inner.value()

    def setValue(self, value: Any) -> None:
        with self.loading():
            self._null.setChecked(value is None)
            self._inner.setEnabled(value is not None)
            if value is not None:
                self._inner.setValue(value)


class RawJsonEditor(BaseEditor):
    """텍스트로 JSON 편집. 파싱 실패 시 마지막 유효값을 유지하고 빨간 테두리로 표시."""

    def __init__(self, schema: JsonSchema, root: JsonSchema, depth: int = 0, parent=None, path: str = ""):
        super().__init__(schema, root, depth, parent, path)
        self._last_valid: Any = default_for(schema, root)
        self._valid = True
        self._text = QtWidgets.QPlainTextEdit()
        self._text.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont))
        self._text.setMinimumHeight(90)
        self._text.setTabChangesFocus(True)
        self._text.setPlaceholderText("JSON")
        self._text.textChanged.connect(self._on_text)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._text)

    def _on_text(self) -> None:
        text = self._text.toPlainText().strip()
        try:
            self._last_valid = json.loads(text) if text else None
            self._valid = True
        except ValueError:
            self._valid = False
        self._text.setStyleSheet("" if self._valid else INVALID_STYLE)
        if self._valid:
            self._emit()

    def isValid(self) -> bool:
        return self._valid

    def value(self) -> Any:
        return self._last_valid

    def setValue(self, value: Any) -> None:
        with self.loading():
            self._last_valid = value
            self._valid = True
            self._text.setPlainText(json.dumps(value, indent=2, ensure_ascii=False))
            self._text.setStyleSheet("")
