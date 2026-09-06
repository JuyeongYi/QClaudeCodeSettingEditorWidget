"""SettingKey / EnvVar enum 과 단건·JSON 갱신 API 테스트."""
import json

import pytest

from qclaudecodesettingeditorwidget import Category, EnvVar, QClaudeCodeSettingEditorWidget, SettingKey
from qclaudecodesettingeditorwidget.categories import CATEGORIES
from qclaudecodesettingeditorwidget.schema import load_env_registry, load_schema


def test_enums_are_in_sync_with_schema_and_registry():
    schema = load_schema()
    assert [m.value for m in SettingKey] == list(schema["properties"])
    assert [m.value for m in EnvVar] == sorted(load_env_registry(schema=schema))
    # 멤버 이름 == 키 ($schema 만 예외)
    assert all(m.name == m.value for m in SettingKey if m.value != "$schema")
    assert SettingKey.schema.value == "$schema"
    assert all(m.name == m.value for m in EnvVar)


def test_enum_behaves_like_str():
    assert SettingKey.model == "model" and hash(SettingKey.model) == hash("model")
    assert str(SettingKey.model) == "model" and f"{SettingKey.model}.x" == "model.x"
    assert {SettingKey.model: 1}["model"] == 1 and {"model": 1}[SettingKey.model] == 1
    assert json.loads(json.dumps({SettingKey.model: EnvVar.API_TIMEOUT_MS})) == {"model": "API_TIMEOUT_MS"}
    assert SettingKey.coerce("schema") == "$schema" and SettingKey.coerce(SettingKey.schema) == "$schema"
    assert SettingKey.coerce("unknownKey") == "unknownKey"
    assert EnvVar.coerce(EnvVar.DEBUG) == "DEBUG"


def test_categories_use_enum_members():
    for _, keys in CATEGORIES:
        assert all(isinstance(k, SettingKey) for k in keys)


@pytest.fixture
def widget(qtbot):
    w = QClaudeCodeSettingEditorWidget(language="en", showManagedOnly=True)
    qtbot.addWidget(w)
    return w


def test_single_setting_accessors(widget):
    assert widget.settingValue(SettingKey.model) is None
    widget.setSettingValue(SettingKey.model, "opus")
    assert widget.settingValue(SettingKey.model) == "opus" == widget.settingValue("model")
    assert widget.rowFor(SettingKey.model).included()
    widget.setSettingValue(SettingKey.permissions, {"allow": ["Read(*)"]})
    assert widget.settings() == {"model": "opus", "permissions": {"allow": ["Read(*)"]}}
    widget.unsetSetting(SettingKey.model)
    assert widget.settingValue(SettingKey.model, "dflt") == "dflt"
    widget.setSettingValue(SettingKey.schema, "https://x")  # $schema
    assert widget.settings()["$schema"] == "https://x"


def test_single_env_accessors(widget):
    assert widget.envValue(EnvVar.API_TIMEOUT_MS) is None
    widget.setEnvValue(EnvVar.API_TIMEOUT_MS, "1200000")
    widget.setEnvValue("MY_VAR", 5)  # 문자열로 저장
    assert widget.envValue(EnvVar.API_TIMEOUT_MS) == "1200000" and widget.envValue("MY_VAR") == "5"
    assert widget.settings()["env"] == {"API_TIMEOUT_MS": "1200000", "MY_VAR": "5"}
    widget.setEnvValue(EnvVar.API_TIMEOUT_MS, None)
    assert widget.settings()["env"] == {"MY_VAR": "5"}


def test_update_setting_json_merges_and_null_unsets(widget):
    widget.setSettings({"model": "opus", "fastMode": True})
    out = widget.UpdateSetting('{"effortLevel": "high", "fastMode": null}')
    assert out == {"model": "opus", "effortLevel": "high"}
    out = widget.UpdateSetting({SettingKey.env: {EnvVar.DEBUG: "1"}})
    assert out["env"] == {"DEBUG": "1"}
    widget.UpdateSetting({"env": None})
    assert "env" not in widget.settings()
    with pytest.raises(ValueError):
        widget.UpdateSetting("[1]")
    with pytest.raises(ValueError):
        widget.UpdateSetting('{"env": 3}')


def test_update_env_json_merges_and_null_unsets(widget):
    widget.setSettings({"env": {"A": "1", "B": "2"}})
    out = widget.UpdateEnv('{"B": null, "C": "3"}')
    assert out == {"A": "1", "C": "3"} == widget.settings()["env"]
    out = widget.UpdateEnv("{}", replace={"Z": "9"})
    assert out == {"Z": "9"} and widget.settings()["env"] == {"Z": "9"}
    widget.UpdateEnv({"Z": None})
    assert "env" not in widget.settings()


def test_updates_work_with_hidden_categories(qtbot):
    w = QClaudeCodeSettingEditorWidget(language="en", categories=Category.MODEL)
    qtbot.addWidget(w)
    w.UpdateSetting({"permissions": {"deny": ["Bash"]}, "model": "sonnet"})
    w.UpdateEnv({"API_TIMEOUT_MS": "7"})
    assert w.settings() == {"model": "sonnet", "permissions": {"deny": ["Bash"]}, "env": {"API_TIMEOUT_MS": "7"}}
    assert w.settingValue(SettingKey.permissions) == {"deny": ["Bash"]}
    assert w.envValue(EnvVar.API_TIMEOUT_MS) == "7"
    w.UpdateEnv({"API_TIMEOUT_MS": None})
    w.unsetSetting(SettingKey.permissions)
    assert w.settings() == {"model": "sonnet"}
