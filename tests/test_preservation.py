"""값 보존(강제 변환 없음)·검증 경고(막지 않음)·툴바 스코프 콤보·initialSettings 위젯 테스트."""
import json
import warnings

import pytest

from qclaudecodesettingeditorwidget import QClaudeCodeSettingEditorWidget, Scope
from qclaudecodesettingeditorwidget.editors import CheckListEditor, NumberEditor, RawJsonEditor
from qclaudecodesettingeditorwidget.toolbar import SCOPE_CHOICES, scope_choice_label
from qclaudecodesettingeditorwidget.validation import SettingValidationWarning

# 폼 편집기가 그대로 담을 수 없는 값들 — 어떤 경로로 들어와도 바뀌지 않고 그대로 나와야 한다
ODD = {
    "effortLevel": "turbo",                                   # enum 밖
    "fastMode": "yes",                                        # 불리언 자리에 문자열
    "cleanupPeriodDays": 99_999_999_999,                      # int32 초과(예전에는 OverflowError)
    "feedbackSurveyRate": 0.1234567891,                       # 표시 자릿수 초과
    "model": 7,                                               # 문자열 자리에 숫자
    "policyHelper": {"timeoutMs": 100},                       # required path 누락 + minimum 위반
    "sandbox": {"enabledPlatforms": ["wsl", "linux", "beos"]},  # enum 밖 항목이 섞인 체크 리스트
    "skillOverrides": {"": "off", "deploy": "maybe"},          # 빈 키 + 값 enum 밖
    "env": {"API_TIMEOUT_MS": 1200000, "DEBUG": True},         # 문자열이 아닌 env 값
}


@pytest.fixture
def widget(qtbot):
    w = QClaudeCodeSettingEditorWidget(language="en", targetScope=Scope.ANY_FILE)
    qtbot.addWidget(w)
    return w


def test_unrepresentable_values_survive_page_building(widget):
    widget.setSettings(ODD, trusted=True)
    assert widget.settings() == ODD                         # 미구축(pending)
    widget.ensureAllPagesBuilt()
    assert widget.settings() == ODD                         # 구축 후에도 그대로
    assert json.loads(widget.GetSetting()) == ODD
    row = widget.rowFor("cleanupPeriodDays")
    assert row is not None and row.slot.isRawFallback()     # 폼 대신 raw JSON 으로 보존 중
    assert widget.rowFor("model").slot.isRawFallback()      # 문자열 자리의 숫자도 문자열로 바꾸지 않는다
    assert not widget.rowFor("permissions").slot.isRawFallback()


def test_raw_fallback_can_switch_back_to_form(widget):
    widget.setSettings({"effortLevel": "turbo"}, trusted=True)
    row = widget.rowFor("effortLevel")
    assert row.slot.isRawFallback() and row.value() == "turbo"
    row.slot._to_form()                                     # 「폼으로 편집」
    assert not row.slot.isRawFallback() and row.value() == "low"
    row.setValue("high")
    assert not row.slot.isRawFallback() and widget.settings() == {"effortLevel": "high"}


def test_checklist_keeps_loaded_order_and_number_bounds(widget):
    sandbox = widget.rowFor("sandbox").editor
    platforms = sandbox.rows["enabledPlatforms"]
    assert isinstance(platforms.editor, CheckListEditor)
    platforms.setValue(["wsl", "linux"])
    assert platforms.value() == ["wsl", "linux"]            # enum 순서(linux, wsl)로 바꾸지 않는다
    rate = widget.rowFor("feedbackSurveyRate").editor
    assert isinstance(rate, NumberEditor)
    ed = NumberEditor({"type": "number", "exclusiveMinimum": 0, "maximum": 1}, {})
    assert ed._spin.minimum() > 0 and not ed.canRepresent(0) and ed.canRepresent(0.5)


def test_api_writes_warn_but_apply(widget):
    with pytest.warns(SettingValidationWarning) as rec:
        widget.UpdateSetting({"effortLevel": "turbo", "model": "opus"})
    assert widget.settings() == {"effortLevel": "turbo", "model": "opus"}
    warning = rec[0].message
    assert isinstance(warning, SettingValidationWarning) and [i.path for i in warning.issues] == ["effortLevel"]
    with pytest.warns(SettingValidationWarning):
        widget.setEnvValue("DEBUG", True)                   # 불리언은 바꾸지 않는다
    widget.setEnvValue("API_TIMEOUT_MS", 5)                  # 숫자는 문자열로(편의 변환, 경고 없음)
    assert widget.settings()["env"] == {"DEBUG": True, "API_TIMEOUT_MS": "5"}


def test_strict_mode_is_opt_in(widget, tmp_path):
    with warnings.catch_warnings():
        warnings.simplefilter("error", SettingValidationWarning)
        with pytest.raises(SettingValidationWarning):
            widget.setSettingValue("cleanupPeriodDays", -1)
        assert widget.settings() == {}                      # 엄격 모드: 적용 전에 멈춘다
    with pytest.warns(SettingValidationWarning):
        widget.setSettingValue("cleanupPeriodDays", -1)
    out = tmp_path / "s.json"
    with warnings.catch_warnings():
        warnings.simplefilter("error", SettingValidationWarning)
        with pytest.raises(SettingValidationWarning):
            widget.saveFile(out)
    assert not out.exists()                                 # 엄격 모드면 쓰지 않는다
    with pytest.warns(SettingValidationWarning):
        widget.saveFile(out)                                # 기본: 경고 후 저장
    assert json.loads(out.read_text("utf-8")) == {"cleanupPeriodDays": -1}


def test_issues_are_shown_in_toolbar_rows_env_and_json(widget, qtbot):
    with qtbot.waitSignal(widget.validationChanged, timeout=1000) as sig:
        widget.setSettings(ODD, trusted=True)
    assert sig.args[0] == len(widget.validationIssues()) > 0
    assert widget._issues_button.isVisibleTo(widget) and "problems" in widget._issues_button.text()
    row = widget.rowFor("policyHelper")                     # 문제 발생 뒤 구축된 행도 표시를 받는다
    assert row._issue_label is not None and "timeoutMs" in row._issue_label.text()
    env = widget.envEditor()
    assert env is not None and "DEBUG" in env._marked and env.variable("DEBUG") is True
    issue = next(i for i in widget.validationIssues() if i.key == "sandbox")
    assert widget.showIssue(issue) and widget._stack.currentWidget() is widget._page_by_key["sandbox"]
    assert widget._json_issues.text().startswith("⚠")


def test_ui_paths_do_not_raise_even_in_strict_apps(widget, tmp_path):
    p = tmp_path / "bad.json"
    p.write_text(json.dumps({"effortLevel": "turbo"}), "utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("error", SettingValidationWarning)
        widget._json.setPlainText('{"model": 3}')
        widget._apply_json_text()                           # JSON 페이지 적용은 막지 않는다
        assert widget.settings() == {"model": 3} and widget._json_error.text() == ""
        with widget._ui_shows_issues():                     # 열기·저장 대화상자가 쓰는 경로
            widget.loadFile(p)
            widget.saveFile(tmp_path / "out.json")
    assert json.loads((tmp_path / "out.json").read_text("utf-8")) == {"effortLevel": "turbo"}


def test_toolbar_scope_selector_and_hidden_count(qtbot):
    w = QClaudeCodeSettingEditorWidget(language="en")
    qtbot.addWidget(w)
    combo = w._scope_selector._combo
    assert [combo.itemText(i) for i in range(len(SCOPE_CHOICES))] == [scope_choice_label(s) for s in SCOPE_CHOICES]
    assert w._scope_selector.scope() == Scope.USER and w._hidden_label.isVisibleTo(w)
    hidden_user = len(w.inapplicableKeys())
    combo.setCurrentIndex(SCOPE_CHOICES.index(Scope.MANAGED))
    assert w.targetScope() == Scope.MANAGED and w.isKeyExposed("claudeMd")
    combo.setCurrentIndex(SCOPE_CHOICES.index(Scope.ANY_FILE))
    assert len(w.inapplicableKeys()) < hidden_user
    w.setTargetScope(Scope.USER | Scope.PROJECT)            # 선택지 밖 조합도 콤보가 따라간다
    assert w._scope_selector.scope() == Scope.USER | Scope.PROJECT
    hidden = QClaudeCodeSettingEditorWidget(language="en", showScopeSelector=False)
    qtbot.addWidget(hidden)
    assert not hidden._scope_selector.isVisibleTo(hidden) and not hidden.showScopeSelector()


def test_initial_settings_object_and_json_text(qtbot):
    data = {"model": "opus", "permissions": {"deny": ["Bash"]}, "claudeMd": "org"}
    w = QClaudeCodeSettingEditorWidget(language="en", initialSettings=data)  # USER 대상: claudeMd 는 숨김 보존
    qtbot.addWidget(w)
    assert w.settings() == data and w._status.text() == "3 keys set"
    w2 = QClaudeCodeSettingEditorWidget(language="en", initialSettings=json.dumps(data))
    qtbot.addWidget(w2)
    assert w2.settings() == data
    with pytest.warns(SettingValidationWarning):
        w3 = QClaudeCodeSettingEditorWidget(language="en", initialSettings={"effortLevel": "turbo"})
    qtbot.addWidget(w3)
    assert w3.settings() == {"effortLevel": "turbo"} and w3._issues_button.isVisibleTo(w3)
    with pytest.raises(ValueError):
        QClaudeCodeSettingEditorWidget(language="en", initialSettings="[1]")


def test_warnings_point_at_the_caller(widget, qtbot, tmp_path):
    """경고 위치가 라이브러리 내부가 아니라 공개 API 를 부른 사용자 코드여야 한다."""
    bad = {"effortLevel": "turbo"}
    f = tmp_path / "s.json"
    f.write_text(json.dumps(bad), "utf-8")
    calls = [lambda: widget.setSettings(bad), lambda: widget.SetSetting(json.dumps(bad)),
             lambda: widget.loadFile(f), lambda: widget.setSettingValue("effortLevel", "turbo"),
             lambda: widget.UpdateSetting(bad), lambda: widget.saveFile(f),
             lambda: widget.setEnvValue("DEBUG", True), lambda: widget.UpdateEnv({"DEBUG": True}),
             lambda: qtbot.addWidget(QClaudeCodeSettingEditorWidget(language="en", initialSettings=bad)),
             lambda: qtbot.addWidget(QClaudeCodeSettingEditorWidget(language="en", initialSettings=json.dumps(bad)))]
    for i, call in enumerate(calls):
        with pytest.warns(SettingValidationWarning) as rec:
            call()
        assert [r.filename for r in rec] == [__file__], i


def test_raw_editor_single_line_mode():
    ed = RawJsonEditor({}, {}, single_line=True)
    ed.setValue({"a": [1, 2]})
    assert ed._line is not None and ed._line.text() == '{"a": [1, 2]}' and ed.value() == {"a": [1, 2]}
    ed._line.setText("{bad")
    assert not ed.isValid() and ed.value() == {"a": [1, 2]}
