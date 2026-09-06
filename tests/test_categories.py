"""카테고리 비트 플래그(Category) 테스트."""
import pytest

from qclaudecodesettingeditorwidget import Category, QClaudeCodeSettingEditorWidget
from qclaudecodesettingeditorwidget.categories import CATEGORIES, categorize
from qclaudecodesettingeditorwidget.schema import load_schema


def test_flag_covers_every_category_id():
    for cid, _ in CATEGORIES:
        assert Category.from_id(cid).id == cid
    assert Category.ALL == Category.SETTINGS | Category.ENV | Category.JSON
    assert Category.parse("model|hooks, ENV") == Category.MODEL | Category.HOOKS | Category.ENV
    with pytest.raises(KeyError):
        Category.parse("nope")


def test_categorize_respects_mask():
    keys = list(load_schema()["properties"])
    assert [cid for cid, _ in categorize(keys, Category.MODEL | Category.HOOKS)] == ["model", "hooks"]
    assert categorize(keys, Category.NONE) == []
    assert categorize(keys, Category.ENV | Category.JSON) == []  # env/json 은 페이지이지 키 분류가 아님


def test_widget_with_subset_hides_pages_and_preserves_hidden_keys(qtbot):
    w = QClaudeCodeSettingEditorWidget(categories=Category.MODEL | Category.HOOKS, language="en")
    qtbot.addWidget(w)
    assert w.categoryIds() == ["model", "hooks"]
    assert w.envEditor() is None
    assert w.rowFor("model") is not None and w.rowFor("permissions") is None
    assert w.categories() == Category.MODEL | Category.HOOKS

    data = {"model": "opus", "permissions": {"allow": ["Read(*)"]}, "env": {"A": "1"}, "hooks": {"Stop": []}}
    w.setSettings(data, trusted=True)    # 파일 로드에 해당: 숨겨진 permissions/env 는 보존만 된다
    assert w.settings() == data
    w.rowFor("model").setValue("sonnet")
    assert w.settings()["model"] == "sonnet"
    assert w.settings()["permissions"] == {"allow": ["Read(*)"]}
    w.clear()
    assert w.settings() == {"permissions": {"allow": ["Read(*)"]}, "env": {"A": "1"}}  # 보존값은 유지
    w.setSettings({}, trusted=True)
    assert w.settings() == {}


def test_widget_env_and_json_only(qtbot):
    w = QClaudeCodeSettingEditorWidget(categories=Category.ENV | Category.JSON, language="en")
    qtbot.addWidget(w)
    assert w.categoryIds() == ["env", "json"]
    assert w.rowFor("model") is None
    w.envEditor().setVariable("API_TIMEOUT_MS", "5")
    assert w.settings() == {"env": {"API_TIMEOUT_MS": "5"}}
    assert w.setCurrentCategory("json")


def test_widget_settings_without_json_page(qtbot):
    w = QClaudeCodeSettingEditorWidget(categories=Category.SETTINGS, language="en")
    qtbot.addWidget(w)
    assert "json" not in w.categoryIds() and "env" not in w.categoryIds()
    assert not w.setCurrentCategory("json")
    w.setSettings({"model": "opus"})
    assert w.GetSettingJsonl() == '{"model":"opus"}'


def test_language_switch_keeps_mask(qtbot):
    w = QClaudeCodeSettingEditorWidget(categories=Category.MODEL, language="en")
    qtbot.addWidget(w)
    w.setLanguage("ko")
    assert w.categoryIds() == ["model"] and w.categoryTitles() == ["모델"]
    w.setLanguage("en")
