"""노출되지 않은 키의 API 우회 차단 테스트."""
import pytest

from qclaudecodesettingeditorwidget import Category, EnvVar, HiddenKeyError, QClaudeCodeSettingEditorWidget, SettingKey


@pytest.fixture
def restricted(qtbot):
    w = QClaudeCodeSettingEditorWidget(language="en", categories=Category.MODEL | Category.HOOKS)
    qtbot.addWidget(w)
    return w


def test_hidden_category_keys_are_rejected_by_single_and_json_apis(restricted):
    w = restricted
    assert w.isKeyExposed(SettingKey.model) and not w.isKeyExposed(SettingKey.permissions) and not w.isKeyExposed("env")
    with pytest.raises(HiddenKeyError) as e:
        w.setSettingValue(SettingKey.permissions, {"allow": ["Read(*)"]})
    assert e.value.keys == ["permissions"]
    with pytest.raises(HiddenKeyError):
        w.unsetSetting(SettingKey.permissions)
    with pytest.raises(HiddenKeyError) as e:
        w.UpdateSetting({"model": "opus", "permissions": {}, "sandbox": {}})
    assert e.value.keys == ["permissions", "sandbox"]
    assert w.settings() == {}  # 부분 적용 없음
    with pytest.raises(HiddenKeyError):
        w.UpdateEnv({"API_TIMEOUT_MS": "1"})
    with pytest.raises(HiddenKeyError):
        w.setEnvValue(EnvVar.DEBUG, "1")
    with pytest.raises(HiddenKeyError):
        w.setSettingValue("env", {"A": "1"})
    with pytest.raises(HiddenKeyError):
        w.setSettingValue("someUnknownKey", 1)  # OTHER 미노출 → 스키마 밖 키도 차단
    with pytest.raises(HiddenKeyError):
        w.setSettings({"model": "opus", "permissions": {"deny": ["Bash"]}})
    assert w.settings() == {}


def test_file_load_preserves_hidden_keys_read_only(restricted, tmp_path):
    w = restricted
    p = tmp_path / "s.json"
    p.write_text('{"model": "opus", "permissions": {"deny": ["Bash"]}, "env": {"A": "1"}, "zzz": 1}', "utf-8")
    w.loadFile(p)
    loaded = {"model": "opus", "permissions": {"deny": ["Bash"]}, "env": {"A": "1"}, "zzz": 1}
    assert w.settings() == loaded
    # 보존값과 동일하면 문서 교체 허용, 바꾸거나 빼면 거부
    w.setSettings({**loaded, "model": "sonnet"})
    assert w.settingValue(SettingKey.model) == "sonnet"
    with pytest.raises(HiddenKeyError):
        w.setSettings({**loaded, "permissions": {"deny": ["Edit"]}})
    with pytest.raises(HiddenKeyError):
        w.setSettings({"model": "opus"})  # 숨긴 키 삭제도 변경
    with pytest.raises(HiddenKeyError):
        w.UpdateSetting({"permissions": None})
    w.clear()
    assert w.settings() == {"permissions": {"deny": ["Bash"]}, "env": {"A": "1"}, "zzz": 1}  # 노출 키만 해제
    w.setSettings({}, trusted=True)
    assert w.settings() == {}


def test_json_page_apply_cannot_change_hidden_keys(qtbot, tmp_path):
    w = QClaudeCodeSettingEditorWidget(language="en", categories=Category.MODEL | Category.JSON)
    qtbot.addWidget(w)
    p = tmp_path / "s.json"
    p.write_text('{"model": "opus", "permissions": {"deny": ["Bash"]}}', "utf-8")
    w.loadFile(p)
    w._json.setPlainText('{"model": "opus", "permissions": {"deny": ["Edit"]}}')
    w._apply_json_text()
    assert "permissions" in w._json_error.text()
    assert w.settings()["permissions"] == {"deny": ["Bash"]}
    w._json.setPlainText('{"model": "haiku", "permissions": {"deny": ["Bash"]}}')
    w._apply_json_text()
    assert w._json_error.text() == "" and w.settings()["model"] == "haiku"


def test_managed_only_hidden_keys_and_nested_paths_are_rejected(qtbot):
    w = QClaudeCodeSettingEditorWidget(language="en")  # showManagedOnly=False
    qtbot.addWidget(w)
    assert not w.isKeyExposed(SettingKey.claudeMd)
    with pytest.raises(HiddenKeyError):
        w.setSettingValue(SettingKey.claudeMd, "x")
    with pytest.raises(HiddenKeyError) as e:
        w.setSettingValue(SettingKey.sandbox, {"enabled": True, "enabledPlatforms": ["linux"]})
    assert e.value.keys == ["sandbox.enabledPlatforms"]
    with pytest.raises(HiddenKeyError):
        w.UpdateSetting({"sandbox": {"network": {"allowManagedDomainsOnly": True}}})
    assert w.settings() == {}
    w.setSettingValue(SettingKey.sandbox, {"enabled": True})  # 비관리형 경로만이면 허용
    assert w.settings() == {"sandbox": {"enabled": True}}
    w.setShowManagedOnly(True)
    w.setSettingValue(SettingKey.claudeMd, "x")
    w.setSettingValue(SettingKey.sandbox, {"enabledPlatforms": ["linux"]})
    assert w.settings() == {"sandbox": {"enabledPlatforms": ["linux"]}, "claudeMd": "x"}


def test_full_widget_allows_everything(qtbot):
    w = QClaudeCodeSettingEditorWidget(language="en", showManagedOnly=True)
    qtbot.addWidget(w)
    w.UpdateSetting({"claudeMd": "x", "permissions": {"deny": ["Bash"]}, "env": {"A": "1"}, "futureKey": [1]})
    assert w.settings() == {"permissions": {"deny": ["Bash"]}, "env": {"A": "1"}, "claudeMd": "x", "futureKey": [1]}
    w.clear()
    assert w.settings() == {}
