"""페이지·env 지연 구축: 생성 비용과 settings()/setSettings() 의미 불변."""
import time

from qclaudecodesettingeditorwidget import Category, QClaudeCodeSettingEditorWidget, Scope, load_schema

SAMPLE = {"model": "opus", "permissions": {"deny": ["Bash"]}, "sandbox": {"enabled": True},
          "claudeMd": "org", "env": {"API_TIMEOUT_MS": "1"}, "futureKey": [1]}


def test_only_first_page_is_built_at_construction(qtbot):
    w = QClaudeCodeSettingEditorWidget(language="en", targetScope=Scope.ANY_FILE)
    qtbot.addWidget(w)
    assert [p.built for p in w._pages] == [True] + [False] * (len(w._pages) - 1)
    assert set(w._rows) == set(w._pages[0].keys)
    assert w._env is None                                  # env 편집기도 아직 없음
    assert set(w._page_by_key) == set(load_schema()["properties"]) - {"env"}


def test_construction_is_fast(qtbot):
    QClaudeCodeSettingEditorWidget(language="en")  # 워밍업(임포트·폰트)
    t = time.perf_counter()
    w = QClaudeCodeSettingEditorWidget(language="en")
    elapsed = time.perf_counter() - t
    qtbot.addWidget(w)
    assert elapsed < 0.3, f"construction took {elapsed*1000:.0f} ms (was ~800 ms before lazy pages)"


def test_settings_roundtrip_without_building_pages(qtbot):
    w = QClaudeCodeSettingEditorWidget(language="en", targetScope=Scope.ANY_FILE)
    qtbot.addWidget(w)
    w.setSettings(SAMPLE)
    assert not w._pages[2].built and w._env is None
    assert w.settings() == SAMPLE                          # 미구축 페이지 값은 pending 에서 나온다
    assert w.settingValue("permissions") == {"deny": ["Bash"]} and w.envValue("API_TIMEOUT_MS") == "1"
    w.setSettingValue("hooks", {"Stop": []})               # 미구축 페이지의 키를 API 로 갱신
    w.UpdateEnv({"DEBUG": "1"})
    assert w.settings()["hooks"] == {"Stop": []} and w.settings()["env"] == {"API_TIMEOUT_MS": "1", "DEBUG": "1"}
    assert w.overlaps() == []
    w._flush_change()                                      # 디바운스 반영 후 카운트는 pending 값으로 계산된다
    assert w._nav.item(2).text().startswith("Permissions  (1/")
    assert not w._pages[2].built and w._env is None


def test_building_a_page_moves_pending_into_rows(qtbot):
    w = QClaudeCodeSettingEditorWidget(language="en", targetScope=Scope.ANY_FILE)
    qtbot.addWidget(w)
    w.setSettings(SAMPLE)
    row = w.rowFor("permissions")                          # 페이지 구축 유발
    assert row is not None and row.included() and row.value() == {"deny": ["Bash"]}
    assert "permissions" not in w._pending
    assert w.settings() == SAMPLE
    row.setValue({"deny": ["Edit"]})
    assert w.settings()["permissions"] == {"deny": ["Edit"]}
    env = w.envEditor()                                    # env 구축 → pending env 반영
    assert env is not None and env.isSet("API_TIMEOUT_MS") and "env" not in w._pending
    w.setCurrentCategory("sandbox")
    assert w.rowFor("sandbox").value() == {"enabled": True}
    w.ensureAllPagesBuilt()
    assert all(p.built for p in w._pages) and w._pending == {}
    assert w.settings()["permissions"] == {"deny": ["Edit"]}


def test_hidden_managed_and_filters_work_on_unbuilt_pages(qtbot):
    w = QClaudeCodeSettingEditorWidget(language="en")        # 대상 USER: 관리형 전용 키 숨김
    qtbot.addWidget(w)
    assert "claudeMd" in w.inapplicableKeys() and not w.isKeyExposed("claudeMd")
    w.setSettings(SAMPLE, trusted=True)
    assert w.settings() == SAMPLE
    idx = w.categoryIds().index("context")
    assert "(0/" not in w._nav.item(idx).text() and "claudeMd" not in w._rows
    w._search.setText("sandbox")
    assert w._nav.item(w.categoryIds().index("sandbox")).text().endswith("(1)")
    w._search.setText("")
    w.setCurrentCategory("context")                         # 이제 구축: 대상 밖 행은 숨겨진 채로
    assert w.rowFor("claudeMd").isHidden() and w.rowFor("claudeMd").included()


def test_language_switch_and_restricted_categories_with_lazy_pages(qtbot):
    w = QClaudeCodeSettingEditorWidget(language="en", categories=Category.MODEL | Category.HOOKS | Category.ENV)
    qtbot.addWidget(w)
    w.setSettings({"model": "opus", "hooks": {"Stop": []}, "env": {"A": "1"}, "permissions": {}}, trusted=True)
    w.setLanguage("ko")
    assert w.settings() == {"model": "opus", "hooks": {"Stop": []}, "env": {"A": "1"}, "permissions": {}}
    assert not w._pages[1].built
    assert w.rowFor("hooks").value() == {"Stop": []}
    w.setLanguage("en")
