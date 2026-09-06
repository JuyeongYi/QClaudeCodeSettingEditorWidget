"""모든 편집기의 공통 베이스."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from PySide6 import QtCore, QtWidgets

from ..schema import JsonSchema, default_for

INVALID_STYLE = "border: 1px solid #d33; background: #fff4f4;"


class BaseEditor(QtWidgets.QWidget):
    """스키마 노드 하나를 편집하는 위젯.

    - value(): 현재 값(JSON 호환 파이썬 객체)
    - setValue(v): 값 로드(변경 시그널 억제)
    - changed: 사용자 조작으로 값이 바뀔 때 발생
    - compact: True 면 한 줄(라벨 오른쪽)에 배치해도 되는 작은 편집기
    """

    changed = QtCore.Signal()
    compact = False

    def __init__(self, schema: JsonSchema, root: JsonSchema, depth: int = 0, parent: QtWidgets.QWidget | None = None,
                 path: str = ""):
        super().__init__(parent)
        self.schema = schema
        self.root = root
        self.level = depth
        self.path = path  # 설명 번역 조회용 경로: "permissions.allow", "hooks.PreToolUse[].matcher"
        self._loading = 0

    # ---- API
    def value(self) -> Any:
        raise NotImplementedError

    def setValue(self, value: Any) -> None:
        raise NotImplementedError

    def reset(self) -> None:
        self.setValue(default_for(self.schema, self.root))

    def isValid(self) -> bool:
        return True

    # ---- helpers
    @contextmanager
    def loading(self) -> Iterator[None]:
        self._loading += 1
        try:
            yield
        finally:
            self._loading -= 1

    def _emit(self, *_: Any) -> None:
        if not self._loading:
            self.changed.emit()
