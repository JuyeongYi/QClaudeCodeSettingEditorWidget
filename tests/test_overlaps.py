"""설정 키 ↔ env 변수 겹침 표시·경고 테스트."""
from qclaudecodesettingeditorwidget import Category, QClaudeCodeSettingEditorWidget
from qclaudecodesettingeditorwidget.schema import load_overlaps, overlaps_by_env


def test_overlap_table_has_known_pairs():
    o = load_overlaps()
    model_envs = {e["env"]: e["precedence"] for e in o["model"]}
    assert model_envs["ANTHROPIC_MODEL"] == "env"            # 문서: 변수를 먼저 읽는다
    assert model_envs["ANTHROPIC_DEFAULT_MODEL"] == "setting"  # 문서: 키 값이 우선
    assert {e["env"] for e in o["autoConnectIde"]} == {"CLAUDE_CODE_AUTO_CONNECT_IDE"}
    assert o["autoConnectIde"][0]["precedence"] == "env"
    assert "model" in [k for k, _ in overlaps_by_env(o)["ANTHROPIC_MODEL"]]


def test_widget_shows_related_and_warns_when_both_set(qtbot):
    w = QClaudeCodeSettingEditorWidget(language="en")
    qtbot.addWidget(w)
    row = w.rowFor("model")
    assert any(r["env"] == "ANTHROPIC_MODEL" for r in row.related)
    assert row.matches("anthropic_model")  # 관련 env 이름으로도 검색된다
    assert w.overlaps() == []
    w.setSettings({"model": "opus", "env": {"ANTHROPIC_MODEL": "claude-opus-5", "UNRELATED": "1"}})
    pairs = w.overlaps()
    assert {"setting": "model", "env": "ANTHROPIC_MODEL", "precedence": "env"} in pairs
    w._flush_change()
    assert not w._overlap_label.isHidden() and "1" in w._overlap_label.text()
    assert w.showEnvVariable("ANTHROPIC_MODEL") and w.categoryIds()[w._nav.currentRow()] == "env"
    env = w.envEditor()
    desc = env._table.item(env._rows["ANTHROPIC_MODEL"], 3).text()
    assert desc.startswith("↔ model")
    w.setSettings({"model": "opus"})
    assert w.overlaps() == []


def test_overlaps_with_hidden_env_page(qtbot):
    w = QClaudeCodeSettingEditorWidget(language="en", categories=Category.MODEL)
    qtbot.addWidget(w)
    w.setSettings({"model": "opus", "env": {"ANTHROPIC_MODEL": "x"}})
    assert w.overlaps()[0]["env"] == "ANTHROPIC_MODEL"  # 숨긴 env 도 passthrough 값으로 판정
    assert not w.showEnvVariable("ANTHROPIC_MODEL")
