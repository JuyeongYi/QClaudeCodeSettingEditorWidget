"""관리형(managed) 전용 키 판별·숨김 테스트."""
from qclaudecodesettingeditorwidget import QClaudeCodeSettingEditorWidget
from qclaudecodesettingeditorwidget.schema import is_managed_only, load_schema


def test_is_managed_only_patterns():
    p = load_schema()["properties"]
    assert is_managed_only(p["claudeMd"])                       # "(Managed settings only) ..."
    assert is_managed_only(p["parentSettingsBehavior"])         # "(Admin/managed settings only) ..."
    assert is_managed_only(p["wslInheritsWindowsSettings"])     # "(Windows managed settings only) ..."
    assert is_managed_only(p["forceLoginGatewayUrl"])           # "Honored only at the managed policy tier"
    assert is_managed_only(p["sandbox"]["properties"]["enabledPlatforms"])  # "Only honored from managed (policy) settings"
    assert not is_managed_only(p["model"])
    assert not is_managed_only(p["disableAllHooks"])            # managed 언급만 있고 전용은 아님
    assert not is_managed_only(p["sandbox"]["properties"]["filesystem"]["properties"]["disabled"])  # user/managed/CLI


def test_default_hides_managed_only_rows_but_keeps_values(qtbot):
    w = QClaudeCodeSettingEditorWidget(language="en")  # showManagedOnly 기본 False
    qtbot.addWidget(w)
    assert not w.showManagedOnly()
    keys = w.managedOnlyKeys()
    assert "claudeMd" in keys and "requiredMinimumVersion" in keys and "model" not in keys
    assert w.rowFor("claudeMd").isHidden() and not w.rowFor("model").isHidden()
    nested = w.rowFor("sandbox").editor.rows["enabledPlatforms"]
    assert nested.managed_only and nested.isHidden()

    data = {"claudeMd": "org rules", "model": "opus", "sandbox": {"enabledPlatforms": ["linux"]}}
    w.setSettings(data, trusted=True)                # 파일 로드에 해당
    assert w.settings() == data                      # 숨겨도 값은 보존
    w._flush_change()
    assert nested.isHidden()

    w.setShowManagedOnly(True)
    assert not w.rowFor("claudeMd").isHidden() and not nested.isHidden()
    w.setShowManagedOnly(False)
    assert w.rowFor("claudeMd").isHidden()


def test_show_managed_only_from_constructor(qtbot):
    w = QClaudeCodeSettingEditorWidget(language="en", showManagedOnly=True)
    qtbot.addWidget(w)
    assert w.showManagedOnly()
    assert not w.rowFor("claudeMd").isHidden()
    assert not w.rowFor("sandbox").editor.rows["enabledPlatforms"].isHidden()


def test_nav_counts_exclude_hidden_managed(qtbot):
    w = QClaudeCodeSettingEditorWidget(language="en", showManagedOnly=True)
    qtbot.addWidget(w)
    idx = w.categoryIds().index("admin")
    w.setSettings({"requiredMinimumVersion": "2.0.0"})
    w._flush_change()
    assert "(1/" in w._nav.item(idx).text()
    w.setShowManagedOnly(False)
    assert w._nav.item(idx).text().startswith("Updates") and "(1/" not in w._nav.item(idx).text()
