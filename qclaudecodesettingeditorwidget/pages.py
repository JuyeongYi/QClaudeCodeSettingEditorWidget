"""카테고리 페이지(지연 구축)와 키 메타데이터.

페이지는 좌측 내비게이션에서 처음 선택될 때(또는 rowFor() 등으로 행이 필요할 때) 구축된다.
구축 전에는 KeyMeta 만으로 검색 매칭·관리형 판별·카운트를 계산하고, 값은 위젯의 _pending 에 보관된다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from PySide6 import QtWidgets

from .editors import PropertyRow
from .i18n import describe, tr
from .schema import JsonSchema, is_managed_only

MUTED = "color: #8a8a8a;"


@dataclass
class KeyMeta:
    """행을 만들지 않고도 알 수 있는 최상위 키 정보."""

    key: str
    schema: JsonSchema
    required: bool = False
    managed_only: bool = False
    related: list[dict[str, str]] = field(default_factory=list)
    _blob: str = ""

    @classmethod
    def build(cls, key: str, schema: JsonSchema, required: bool, related: list[dict[str, str]] | None) -> "KeyMeta":
        related = list(related or [])
        desc = schema.get("description", "")
        blob = " ".join([key, describe(key, desc), desc, *(r["env"] for r in related)]).lower()
        return cls(key, schema, required, is_managed_only(schema), related, blob)

    def matches(self, text: str) -> bool:
        return text.lower() in self._blob


class _Page(QtWidgets.QWidget):
    """카테고리 한 페이지. build() 전에는 제목만 있고, 행은 처음 필요할 때 만든다."""

    def __init__(self, category_id: str, title: str, keys: list[str], meta: dict[str, KeyMeta],
                 row_factory: Callable[[str], PropertyRow], is_set: Callable[[str], bool], parent=None):
        super().__init__(parent)
        self.category_id = category_id
        self.title = title
        self.keys = list(keys)
        self._meta = meta
        self._row_factory = row_factory
        self._is_set = is_set
        self.rows: list[PropertyRow] = []
        self._separators: list[QtWidgets.QFrame] = []
        self.built = False

        self._body = QtWidgets.QWidget()
        self._layout = QtWidgets.QVBoxLayout(self._body)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(6)
        heading = QtWidgets.QLabel(title)
        f = heading.font()
        f.setPointSize(f.pointSize() + 2)
        f.setBold(True)
        heading.setFont(f)
        self._layout.addWidget(heading)
        self.empty_label = QtWidgets.QLabel(tr("No matches"))
        self.empty_label.setStyleSheet(MUTED)
        self.empty_label.hide()
        self._layout.addWidget(self.empty_label)
        self._layout.addStretch(1)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._body)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(scroll)

    # ---- 구축
    def build(self) -> None:
        """행을 실제로 만든다(한 번만). 값은 row_factory 가 pending 에서 채운다."""
        if self.built:
            return
        self.built = True
        insert_at = self._layout.count() - 1  # stretch 앞
        self._body.setUpdatesEnabled(False)
        try:
            for key in self.keys:
                row = self._row_factory(key)
                self.rows.append(row)
                self._layout.insertWidget(insert_at, row)
                line = QtWidgets.QFrame()
                line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
                line.setStyleSheet("color: palette(midlight);")
                self._separators.append(line)
                self._layout.insertWidget(insert_at + 1, line)
                insert_at += 2
        finally:
            self._body.setUpdatesEnabled(True)

    # ---- 필터·카운트
    def _visible_keys(self, text: str, only_set: bool, show_managed: bool) -> list[str]:
        out = []
        for key in self.keys:
            m = self._meta[key]
            if not show_managed and m.managed_only:
                continue
            if text and not m.matches(text):
                continue
            if only_set and not self._is_set(key):
                continue
            out.append(key)
        return out

    def count(self, text: str, only_set: bool, show_managed: bool) -> tuple[int, int, int]:
        """(조건에 맞는 키 수, 설정된 키 수, 표시 대상 키 수) — 구축 여부와 무관하게 계산."""
        eligible = [k for k in self.keys if show_managed or not self._meta[k].managed_only]
        n_set = sum(1 for k in eligible if self._is_set(k))
        return len(self._visible_keys(text, only_set, show_managed)), n_set, len(eligible)

    def applyFilter(self, text: str, only_set: bool, show_managed: bool = True) -> int:
        """구축된 페이지는 행 표시를 갱신하고, 아니면 카운트만 돌려준다."""
        visible = set(self._visible_keys(text, only_set, show_managed))
        if self.built:
            for r, sep in zip(self.rows, self._separators):
                ok = r.key in visible
                r.setVisible(ok)
                sep.setVisible(ok)
            self.empty_label.setVisible(not visible)
        return len(visible)
