"""tools/build_translations.py 의 .ts 갱신 규칙(번역 보존·새 항목/원문 변경 unfinished) 단위 테스트."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import build_translations as bt  # noqa: E402
from qclaudecodesettingeditorwidget.constants import CONTEXT_SCHEMA, CONTEXT_UI  # noqa: E402

LANG = "xx"


@pytest.fixture
def locales(tmp_path, monkeypatch):
    monkeypatch.setattr(bt, "LOCALES", tmp_path)
    return tmp_path


def _update(paths: dict[str, str], imports: dict[str, dict[str, str]] | None = None) -> dict[str, bt.TsMessage]:
    path = bt.update_language(LANG, ["_name"], paths, imports)
    return bt.read_ts(path)[CONTEXT_SCHEMA]


@pytest.mark.usefixtures("locales")
def test_changed_english_source_marks_translation_unfinished_but_keeps_text():
    _update({"model": "Model to use.", "env.A": "Set to 1."},
            {CONTEXT_SCHEMA: {"model": "사용할 모델.", "env.A": "1로 설정."}, CONTEXT_UI: {"_name": "X"}})

    data = _update({"model": "Model to use.", "env.A": "Set to 1 to enable A.", "env.B": "New."})

    assert data["model"].done
    assert data["env.A"] == bt.TsMessage("1로 설정.", "Set to 1 to enable A.", True)
    assert data["env.B"] == bt.TsMessage("", "New.", True)


@pytest.mark.usefixtures("locales")
def test_unfinished_flag_survives_rerun_until_translation_imported():
    _update({"env.A": "Old."}, {CONTEXT_SCHEMA: {"env.A": "옛 번역."}})
    _update({"env.A": "New."})

    assert not _update({"env.A": "New."})["env.A"].done      # 두 번째 갱신에서도 다시 볼 대상으로 남는다
    assert _update({"env.A": "New."}, {CONTEXT_SCHEMA: {"env.A": "새 번역."}})["env.A"] == \
        bt.TsMessage("새 번역.", "New.", False)
