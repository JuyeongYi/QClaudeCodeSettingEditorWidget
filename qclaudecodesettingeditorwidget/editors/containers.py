"""컨테이너 편집기: object / dict(additionalProperties) / array / anyOf / nullable.

자식 값은 모두 ValueSlot(PropertyRow 포함)을 거쳐 들어가므로, 폼이 담을 수 없는 값도 바꾸지 않고 보존된다.
"""
from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from ..constants import ERROR_COLOR, INVALID_STYLE, MUTED
from ..i18n import describe, join_path, tr
from ..schema import JsonSchema, default_for, json_equal, json_in, resolve_ref, value_matches, variant_label
from ..validation import errors_only, validate
from .base import BaseEditor
from .raw import RawJsonEditor
from .row import PropertyRow
from .slot import ValueSlot

FRAME_STYLE = "QFrame#nested { border-left: 2px solid palette(mid); }"


def _tool_button(text: str, tip: str, slot) -> QtWidgets.QToolButton:
    b = QtWidgets.QToolButton()
    b.setText(text)
    b.setToolTip(tip)
    b.clicked.connect(slot)
    return b


def _slot_for(schema: JsonSchema, root: JsonSchema, depth: int, path: str) -> ValueSlot:
    from . import create_editor  # 순환 임포트 회피

    return ValueSlot(create_editor(schema, root, depth, path=path))


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

    def canRepresent(self, value: Any) -> bool:  # noqa: N802
        return isinstance(value, dict)

    def setValue(self, value: Any) -> None:
        if not isinstance(value, dict):
            return
        with self.loading():
            extras: dict[str, Any] = {}
            for k, v in value.items():
                if k in self.rows:
                    self.rows[k].setValue(v)
                else:
                    extras[k] = v
            for k, row in self.rows.items():
                if k not in value:
                    row.resetValue()
                    row.setIncluded(False, force=True)  # 빠진 required 키도 빠진 그대로(검증이 알린다)
            if self._extra is not None:
                self._extra.setValue(extras)
                self._passthrough = {}
            else:
                self._passthrough = extras


# --------------------------------------------------------------------------- DictEditor
class _DictRow:
    __slots__ = ("wrap", "key_edit", "editor", "keep_empty")

    def __init__(self, wrap: QtWidgets.QWidget, key_edit: QtWidgets.QLineEdit, editor: ValueSlot, keep_empty: bool):
        self.wrap, self.key_edit, self.editor, self.keep_empty = wrap, key_edit, editor, keep_empty


class DictEditor(BaseEditor):
    """additionalProperties 스키마를 값으로 갖는 자유 키 맵.

    키가 propertyNames 패턴에 안 맞거나 중복이면 빨갛게 표시한다(중복 키는 마지막 것만 남는다).
    로드한 값의 빈 키("")는 보존하고, 사용자가 추가한 뒤 이름을 비워 둔 행은 출력에서 뺀다.
    """

    def __init__(self, schema: JsonSchema, root: JsonSchema, depth: int = 0, parent=None, path: str = ""):
        super().__init__(schema, root, depth, parent, path)
        addl = schema.get("additionalProperties")
        self._value_schema: JsonSchema = resolve_ref(addl, root) if isinstance(addl, dict) else {}
        pn = schema.get("propertyNames", {})
        self._key_schema: JsonSchema = pn if isinstance(pn, dict) else {}
        self._rows: list[_DictRow] = []

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

    def _add_row(self, key: str, value: Any, focus: bool = False, loaded: bool = False) -> None:
        wrap = QtWidgets.QWidget()
        h = QtWidgets.QHBoxLayout(wrap)
        h.setContentsMargins(0, 0, 0, 0)
        key_edit = QtWidgets.QLineEdit(key)
        key_edit.setPlaceholderText(tr("key"))
        key_edit.setMinimumWidth(140)
        key_edit.setMaximumWidth(260)
        editor = _slot_for(self._value_schema, self.root, self.level + 1, join_path(self.path, "*"))
        editor.setValue(value)
        editor.changed.connect(self._emit)
        entry = _DictRow(wrap, key_edit, editor, keep_empty=loaded and key == "")
        key_edit.textChanged.connect(lambda: self._on_key_edited(entry))
        rm = _tool_button("✕", tr("Remove"), lambda: self._remove_row(entry))
        h.addWidget(key_edit)
        h.addWidget(QtWidgets.QLabel(":"))
        h.addWidget(editor, 1)
        h.addWidget(rm, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        self._rows.append(entry)
        self._list.addWidget(wrap)
        if not loaded:
            self._validate_keys()
        if focus:
            key_edit.setFocus()
            self._emit()

    def _on_key_edited(self, entry: _DictRow) -> None:
        entry.keep_empty = False
        self._validate_keys()
        self._emit()

    def _remove_row(self, entry: _DictRow) -> None:
        if entry in self._rows:
            self._rows.remove(entry)
            entry.wrap.setParent(None)
            entry.wrap.deleteLater()
            self._validate_keys()
            self._emit()

    def _validate_keys(self) -> None:
        seen: dict[str, int] = {}
        for r in self._rows:
            seen[r.key_edit.text()] = seen.get(r.key_edit.text(), 0) + 1
        for r in self._rows:
            text = r.key_edit.text()
            problem = ""
            if text and self._key_schema:
                bad = errors_only(validate(self._key_schema, text, self.root))
                problem = bad[0].message if bad else ""
            if seen[text] > 1 and (text or r.keep_empty):
                problem = tr("Duplicate key: only the last entry is kept")
            r.key_edit.setStyleSheet(INVALID_STYLE if problem else "")
            r.key_edit.setToolTip(problem)

    def value(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for r in self._rows:
            k = r.key_edit.text()
            if k or r.keep_empty:
                out[k] = r.editor.value()
        return out

    def canRepresent(self, value: Any) -> bool:  # noqa: N802
        return isinstance(value, dict)

    def setValue(self, value: Any) -> None:
        if not isinstance(value, dict):
            return
        with self.loading():
            for r in self._rows:
                r.wrap.setParent(None)
                r.wrap.deleteLater()
            self._rows.clear()
            for k, v in value.items():
                self._add_row(k, v, loaded=True)
            self._validate_keys()


# --------------------------------------------------------------------------- 배열
class StringListEditor(BaseEditor):
    """문자열 배열: 인라인 편집 리스트 + 추가/삭제/이동. 항목 스키마(pattern 등)·uniqueItems 위반은 빨갛게 표시."""

    def __init__(self, schema: JsonSchema, root: JsonSchema, depth: int = 0, parent=None, path: str = ""):
        super().__init__(schema, root, depth, parent, path)
        self._item_schema = resolve_ref(schema.get("items", {}), root)
        self._marking = False  # _mark_items 가 항목 색을 바꾸는 동안 itemChanged 무시
        self._list = QtWidgets.QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.setMinimumHeight(60)
        self._list.setMaximumHeight(160)
        self._list.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
        self._list.itemChanged.connect(self._on_item_changed)
        ex = self._item_schema.get("examples") or schema.get("examples")
        hint = ""
        if isinstance(ex, list) and ex:
            sample = ex[0] if not isinstance(ex[0], list) else ", ".join(map(str, ex[0]))
            hint = tr("e.g. {value}", value=sample)
        self._tip = describe(path + "[]", self._item_schema.get("description", "")) or hint
        self._list.setToolTip(self._tip)

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
        self._changed_by_user()

    def _remove(self) -> None:
        row = self._list.currentRow()
        if row >= 0:
            self._list.takeItem(row)
            self._changed_by_user()

    def _move(self, delta: int) -> None:
        row = self._list.currentRow()
        new = row + delta
        if row < 0 or not (0 <= new < self._list.count()):
            return
        it = self._list.takeItem(row)
        self._list.insertItem(new, it)
        self._list.setCurrentRow(new)
        self._changed_by_user()

    def _on_item_changed(self, *_: Any) -> None:
        if not self._marking:
            self._changed_by_user()

    def _changed_by_user(self) -> None:
        self._mark_items()
        self._emit()

    def _mark_items(self) -> None:
        """항목별 문제(패턴 불일치·중복)를 빨간 글자 + 툴팁으로 표시."""
        values = self.value()
        unique = self.schema.get("uniqueItems") is True
        self._marking = True
        try:
            for i, text in enumerate(values):
                problem = ""
                if text and self._item_schema:
                    bad = errors_only(validate(self._item_schema, text, self.root))
                    problem = bad[0].message if bad else ""
                if unique and any(values[j] == text for j in range(i)):
                    problem = tr("Duplicate item")
                it = self._list.item(i)
                it.setForeground(QtGui.QBrush(QtGui.QColor(ERROR_COLOR)) if problem else QtGui.QBrush())
                it.setToolTip(problem or self._tip)
        finally:
            self._marking = False

    def value(self) -> list[str]:
        return [self._list.item(i).text() for i in range(self._list.count())]

    def canRepresent(self, value: Any) -> bool:  # noqa: N802
        return isinstance(value, list) and all(isinstance(v, str) for v in value)

    def setValue(self, value: Any) -> None:
        if not self.canRepresent(value):
            return
        with self.loading():
            self._list.clear()
            for v in value:
                self._list.addItem(self._new_item(v))
            self._mark_items()


class CheckListEditor(BaseEditor):
    """enum 문자열 배열: 체크 리스트. 로드한 순서를 유지하고, 새로 켠 항목은 enum 순서로 뒤에 붙인다."""

    def __init__(self, schema: JsonSchema, root: JsonSchema, depth: int = 0, parent=None, path: str = ""):
        super().__init__(schema, root, depth, parent, path)
        items = resolve_ref(schema.get("items", {}), root)
        self._enum: list[Any] = list(items.get("enum", []))
        self._order: list[Any] = []
        self._list = QtWidgets.QListWidget()
        self._list.setMaximumHeight(140)
        for v in self._enum:
            it = QtWidgets.QListWidgetItem(str(v))
            it.setFlags(QtCore.Qt.ItemFlag.ItemIsUserCheckable | QtCore.Qt.ItemFlag.ItemIsEnabled)
            it.setCheckState(QtCore.Qt.CheckState.Unchecked)
            self._list.addItem(it)
        self._list.itemChanged.connect(self._emit)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._list)

    def _checked(self) -> list[Any]:
        return [v for i, v in enumerate(self._enum)
                if self._list.item(i).checkState() == QtCore.Qt.CheckState.Checked]

    def value(self) -> list[Any]:
        checked = self._checked()
        kept = [v for v in self._order if json_in(v, checked)]
        return kept + [v for v in checked if not json_in(v, kept)]

    def canRepresent(self, value: Any) -> bool:  # noqa: N802
        """enum 밖 항목·중복 항목이 있으면 체크 리스트로는 그대로 담을 수 없다."""
        if not isinstance(value, list) or not all(json_in(v, self._enum) for v in value):
            return False
        return all(not json_equal(value[i], value[j]) for j in range(len(value)) for i in range(j))

    def setValue(self, value: Any) -> None:
        if not self.canRepresent(value):
            return
        with self.loading():
            self._order = list(value)
            for i, v in enumerate(self._enum):
                on = json_in(v, value)
                self._list.item(i).setCheckState(QtCore.Qt.CheckState.Checked if on else QtCore.Qt.CheckState.Unchecked)


class ListEditor(BaseEditor):
    """임의 항목 배열: 항목마다 자식 편집기(ValueSlot) + 이동/삭제."""

    def __init__(self, schema: JsonSchema, root: JsonSchema, depth: int = 0, parent=None, path: str = ""):
        super().__init__(schema, root, depth, parent, path)
        self._item_schema = resolve_ref(schema.get("items", {}), root)
        self._items: list[tuple[QtWidgets.QWidget, ValueSlot, QtWidgets.QLabel]] = []
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
        editor = _slot_for(self._item_schema, self.root, self.level + 1, self.path + "[]")
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

    def canRepresent(self, value: Any) -> bool:  # noqa: N802
        return isinstance(value, list)

    def setValue(self, value: Any) -> None:
        if not isinstance(value, list):
            return
        with self.loading():
            for frame, _, _ in self._items:
                frame.setParent(None)
                frame.deleteLater()
            self._items.clear()
            for v in value:
                self._add_item(v)


# --------------------------------------------------------------------------- anyOf / nullable
class AnyOfEditor(BaseEditor):
    """anyOf/oneOf: 변형 선택 콤보 + 스택. 값 로드 시 구조가 맞고 그대로 담을 수 있는 변형을 고르고, 없으면 raw JSON."""

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
                ed.reset()
            else:
                ed = RawJsonEditor(self.schema, self.root, self.level + 1, path=self.path)
                ed.setValue(None)
            ed.changed.connect(self._emit)
            old = self._stack.widget(idx)
            if old is not None:
                self._stack.removeWidget(old)
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
            if value_matches(v, value, self.root) and self._ensure_editor(i).canRepresent(value):
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

    def canRepresent(self, value: Any) -> bool:  # noqa: N802
        return value is None or self._inner.canRepresent(value)

    def setValue(self, value: Any) -> None:
        with self.loading():
            self._null.setChecked(value is None)
            self._inner.setEnabled(value is not None)
            if value is not None:
                self._inner.setValue(value)


__all__ = ["AnyOfEditor", "CheckListEditor", "DictEditor", "ListEditor", "NullableEditor", "ObjectEditor",
           "PropertyRow", "RawJsonEditor", "StringListEditor"]
