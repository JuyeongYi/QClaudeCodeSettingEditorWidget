"""위젯 파괴 뒤 지연 갱신 타이머가 발화해도 죽지 않아야 한다.

재현: 부모 없는 위젯 생성 → setSettings()(0ms 디바운스 예약) → 위젯 파괴 → 이벤트 처리.
예전 구현(QTimer.singleShot(0, self._flush_change))은 파괴된 PropertyRow 에 접근해
RuntimeError("Internal C++ object ... already deleted") 를 냈다.
"""
import gc

import shiboken6
from PySide6 import QtCore, QtWidgets

from qclaudecodesettingeditorwidget import QClaudeCodeSettingEditorWidget


def _pump() -> None:
    for _ in range(3):
        QtWidgets.QApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        QtWidgets.QApplication.processEvents()


def test_pending_refresh_does_not_fire_after_delete_later(qapp):
    w = QClaudeCodeSettingEditorWidget(language="en", showManagedOnly=True)
    w.setSettings({"model": "opus"})
    w.deleteLater()
    _pump()
    assert not shiboken6.isValid(w)


def test_pending_refresh_does_not_fire_after_explicit_delete(qapp):
    w = QClaudeCodeSettingEditorWidget(language="en", showManagedOnly=True)
    w.setSettings({"model": "opus"})
    shiboken6.delete(w)  # C++ 객체를 즉시 파괴 (파이썬 참조는 남아 있음)
    _pump()


def test_pending_refresh_does_not_fire_after_python_release(qapp):
    w = QClaudeCodeSettingEditorWidget(language="en", showManagedOnly=True)
    w.setSettings({"model": "opus"})
    del w
    gc.collect()
    _pump()


def test_flush_still_runs_for_live_widget(qtbot):
    w = QClaudeCodeSettingEditorWidget(language="en", showManagedOnly=True)
    qtbot.addWidget(w)
    with qtbot.waitSignal(w.settingChanged, timeout=1000):
        w.setSettings({"model": "opus"})
    assert w._status.text() == "1 keys set"
    with qtbot.waitSignal(w.settingChanged, timeout=1000):
        w.setSettingValue("model", "sonnet")
        w.setSettingValue("fastMode", True)   # 같은 턴의 변경은 한 번으로 합쳐진다
    assert w._status.text() == "2 keys set"
