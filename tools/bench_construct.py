"""위젯 생성 시간 벤치: python tools/bench_construct.py [반복수]

오프스크린으로 QClaudeCodeSettingEditorWidget() 을 여러 번 만들어 최소/중앙값(ms)을 찍는다.
페이지·env 지연 구축 전 ~800 ms, 후 수십 ms 가 기대치다.
"""
from __future__ import annotations

import os
import statistics
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6 import QtWidgets  # noqa: E402

from qclaudecodesettingeditorwidget import Category, QClaudeCodeSettingEditorWidget, Scope  # noqa: E402
from qclaudecodesettingeditorwidget.constants import ENV_LANG, SOURCE_LANG  # noqa: E402

os.environ.setdefault(ENV_LANG, SOURCE_LANG)


def bench(label: str, fn, n: int) -> None:
    times = []
    for _ in range(n):
        t = time.perf_counter()
        w = fn()
        times.append((time.perf_counter() - t) * 1000)
        if hasattr(w, "deleteLater"):
            w.deleteLater()
        QtWidgets.QApplication.processEvents()
    print(f"{label:48s} min {min(times):7.1f} ms   median {statistics.median(times):7.1f} ms  (n={n})")


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    QClaudeCodeSettingEditorWidget()  # 워밍업(임포트·폰트 캐시)
    bench("QClaudeCodeSettingEditorWidget()", lambda: QClaudeCodeSettingEditorWidget(), n)
    bench("… targetScope=Scope.ANY_FILE", lambda: QClaudeCodeSettingEditorWidget(targetScope=Scope.ANY_FILE), n)
    bench("… categories=Category.ENV | JSON", lambda: QClaudeCodeSettingEditorWidget(categories=Category.ENV | Category.JSON), n)

    def full():
        w = QClaudeCodeSettingEditorWidget()
        w.ensureAllPagesBuilt()
        return w

    bench("… + ensureAllPagesBuilt() (전부 구축)", full, n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
