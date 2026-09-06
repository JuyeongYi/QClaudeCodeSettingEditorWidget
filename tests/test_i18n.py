"""현지화(QTranslator/.ts/.qm) 테스트."""
import pytest

from qclaudecodesettingeditorwidget import QClaudeCodeSettingEditorWidget, i18n
from qclaudecodesettingeditorwidget.i18n import TsTranslator, describe, tr

TS_XX = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="xx">
  <context><name>qccse</name>
    <message><source>_name</source><translation>Testish</translation></message>
    <message><source>Open…</source><translation>Xopen</translation></message>
    <message><source>{n} keys set</source><translation>{n} xkeys</translation></message>
    <message><source>Save…</source><translation type="unfinished"></translation></message>
  </context>
  <context><name>schema</name>
    <message><source>model</source><translation>Xmodel desc</translation></message>
  </context>
</TS>
"""


@pytest.fixture(autouse=True)
def _restore_language(qapp):
    yield
    i18n.set_language("en")


def test_source_language_passthrough(qapp):
    i18n.set_language("en")
    assert tr("Open…") == "Open…"
    assert tr("{n} keys set", n=3) == "3 keys set"
    assert describe("model", "default text") == "default text"


def test_bundled_korean(qapp):
    assert "ko" in i18n.available_languages()
    assert i18n.set_language("ko") == "ko"
    assert tr("Open…") == "열기…"
    assert tr("{n} keys set", n=3) == "3개 키 설정됨"
    assert tr("Auth & API") == "인증·API"
    assert i18n.language_name("ko") == "한국어"


def test_drop_in_ts_file_enables_language(qapp, tmp_path):
    (tmp_path / "qccse_xx.ts").write_text(TS_XX, "utf-8")
    t = TsTranslator(tmp_path / "qccse_xx.ts")
    assert len(t) == 4 and t.translate("qccse", "Save…") == ""  # unfinished 는 무시
    i18n.add_locale_dir(tmp_path)
    try:
        assert "xx" in i18n.available_languages()
        assert i18n.language_name("xx") == "Testish"
        i18n.set_language("xx")
        assert tr("Open…") == "Xopen"
        assert tr("Save…") == "Save…"  # 미번역 → 영어 원문
        assert tr("{n} keys set", n=2) == "2 xkeys"
        assert describe("model", "english") == "Xmodel desc"
        assert describe("permissions", "english") == "english"
    finally:
        i18n._extra_dirs.remove(tmp_path)


def test_widget_set_language_keeps_settings(qtbot):
    w = QClaudeCodeSettingEditorWidget(language="en")
    qtbot.addWidget(w)
    w.setSettings({"model": "opus", "env": {"API_TIMEOUT_MS": "1"}})
    assert w.categoryTitles()[0] == "Auth & API"
    assert w.setLanguage("ko") == "ko"
    assert w.categoryTitles()[0] == "인증·API"
    assert w.language() == "ko"
    assert w.settings() == {"model": "opus", "env": {"API_TIMEOUT_MS": "1"}}
    assert w.setCurrentCategory("hooks") and w.setCurrentCategory("훅")
    w.setLanguage("en")
    assert w.categoryTitles()[0] == "Auth & API"
    assert w.settings()["model"] == "opus"
