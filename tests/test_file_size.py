"""소스 파일 크기 상한 — 비대해지면 기능을 더하기 전에 분리한다(800줄 검토, 1200줄 금지)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIMIT = 800
# 상한을 넘겨도 되는 파일과 그 파일만의 상한. 자동 생성 파일도 1200 을 넘기면 생성기에서 분리한다.
ALLOW: dict[str, int] = {}
HARD_LIMIT = 1200


def test_python_files_stay_under_size_limit():
    over = []
    for py in sorted(ROOT.glob("*/**/*.py")):
        rel = py.relative_to(ROOT).as_posix()
        if rel.split("/")[0] not in ("qclaudecodesettingeditorwidget", "tools", "tests") or "__pycache__" in rel:
            continue
        n = len(py.read_text("utf-8").splitlines())
        limit = min(ALLOW.get(rel, LIMIT), HARD_LIMIT)
        if n > limit:
            over.append(f"{rel}: {n} > {limit}")
    assert not over, "split these files first:\n" + "\n".join(over)
