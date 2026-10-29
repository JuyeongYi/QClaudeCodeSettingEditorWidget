"""키 메타데이터(SettingInfo)·편집 대상 스코프·Claude Code 버전 필터 테스트."""
import ast
import json
from pathlib import Path

import pytest
from PySide6 import QtWidgets

from qclaudecodesettingeditorwidget import (
    NESTED_SETTINGS,
    HiddenKeyError,
    JsonType,
    QClaudeCodeSettingEditorWidget,
    Scope,
    SettingKey,
    Topic,
    Version,
    __version__,
    setting_info,
)
from qclaudecodesettingeditorwidget import keys
from qclaudecodesettingeditorwidget.editors import EnumEditor, ObjectEditor, StringEditor
from qclaudecodesettingeditorwidget.spec import SettingInfo


# --------------------------------------------------------------------------- 메타데이터 (Qt 불필요)
def test_scopes_come_from_docs_scope_column():
    assert SettingKey.model.info.scope == Scope.ANY_FILE
    assert SettingKey.claudeMd.info.scope == Scope.MANAGED
    assert SettingKey.availableModelsMatch.info.scope == Scope.MANAGED
    assert SettingKey.askUserQuestionTimeout.info.scope == Scope.USER | Scope.MANAGED
    assert SettingKey.syncClaudeAiSkills.info.scope == Scope.USER | Scope.LOCAL | Scope.MANAGED
    assert SettingKey.autoConnectIde.info.scope == Scope.GLOBAL_CONFIG       # ~/.claude.json
    assert setting_info("sandbox.bwrapPath").scope == Scope.MANAGED            # 중첩 경로(문서)
    assert setting_info("sandbox.enabledPlatforms").scope == Scope.MANAGED     # 문서에 없음 → 스키마 설명으로 판별
    assert setting_info("worktree.location").scope == Scope.USER
    assert setting_info("nope.nothing") is None


def test_setting_info_carries_type_default_values_and_versions():
    i = SettingKey.availableModelsMatch.info
    assert (i.type, i.default, i.values, i.since) == (JsonType.STRING, "prefix", ("prefix", "exact"), Version(2, 1, 283))
    assert i.topic is Topic.MODEL and SettingKey.teammateDefaultModel.info.type == JsonType.STRING | JsonType.NULL
    assert i.in_docs and not i.in_schemastore                                 # schemastore 에 없던 키
    assert SettingKey.maxEffortLevel.info.values == ("low", "medium", "high", "xhigh", "max")
    v = SettingKey.voiceEnabled.info
    assert v.deprecated and v.deprecated_since == Version(2, 1, 92) and v.replaced_by is SettingKey.voice.info
    assert SettingKey.taskOutputMaxChars.info.removed == Version(2, 1, 277)
    assert SettingKey.schema.info.key == "$schema" and not SettingKey.schema.info.in_docs
    assert all(isinstance(m.info, SettingInfo) and m.info.key == m.value for m in SettingKey)
    assert all(info.key == path for path, info in NESTED_SETTINGS.items())


def test_setting_info_version_predicates():
    i = SettingInfo("x", since=Version(2, 1, 100), removed=Version(2, 1, 200), deprecated=True,
                    deprecated_since=Version(2, 1, 150))
    assert not i.available_in("2.1.99") and i.available_in("2.1.100") and not i.available_in("2.1.200")
    assert i.available_in(None) and i.available_in(Version(2, 1, 150))
    assert not i.deprecated_in("2.1.149") and i.deprecated_in("2.1.150")
    assert SettingInfo("y").available_in("0.1")                               # 버전 미상 = 항상 있음
    assert Version.parse("v2.1") == Version(2, 1, 0) and str(Version(2, 1, 283)) == "2.1.283"
    with pytest.raises(ValueError):
        Version.parse("latest")
    assert Scope.parse("user|managed") == Scope.USER | Scope.MANAGED
    assert JsonType.parse("string|null") == JsonType.STRING | JsonType.NULL


def test_package_version_is_claude_code_version():
    assert QClaudeCodeSettingEditorWidget.latestVersion() == __version__
    known = [i.since for i in map(lambda m: m.info, SettingKey) if i.since]
    assert max(known) <= Version.parse(__version__)


def test_generated_metadata_uses_constants_not_strings():
    """keys.py 의 SettingInfo 는 스코프·타입·버전·주제·대체 키를 상수 참조로만 적는다(문자열은 키·JSON 값뿐)."""
    tree = ast.parse(Path(keys.__file__).read_text("utf-8"))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "SettingInfo"]
    assert len(calls) == len(SettingKey) + len(NESTED_SETTINGS)
    typed = {"scope", "type", "since", "deprecated_since", "replaced_by", "removed", "topic"}
    assert [(ast.literal_eval(c.args[0]), kw.arg) for c in calls for kw in c.keywords
            if kw.arg in typed and isinstance(kw.value, ast.Constant)] == []
    paths = [ast.literal_eval(c.args[0]) for c in calls]
    assert len(paths) == len(set(paths))                                       # 키 문자열은 한 번씩만


# --------------------------------------------------------------------------- 위젯: 스코프
def _visible(w, key):
    return not w.rowFor(key).isHidden()


def test_default_targets_user_file(qtbot):
    w = QClaudeCodeSettingEditorWidget(language="en")
    qtbot.addWidget(w)
    assert w.targetScope() == Scope.USER and w.targetVersion() is None
    assert not _visible(w, "claudeMd") and not _visible(w, "autoConnectIde")   # Managed / Global config
    assert _visible(w, "askUserQuestionTimeout") and _visible(w, "model")
    assert {"claudeMd", "autoConnectIde"} <= set(w.inapplicableKeys())
    nested = w.rowFor("sandbox").editor.rows["bwrapPath"]
    assert nested.info.scope == Scope.MANAGED and nested.isHidden()

    data = {"claudeMd": "org rules", "model": "opus", "sandbox": {"bwrapPath": "/usr/bin/bwrap"}}
    w.setSettings(data, trusted=True)                                          # 파일 로드에 해당
    assert w.settings() == data                                                # 숨겨도 값은 보존


def test_project_scope_hides_user_only_keys(qtbot):
    w = QClaudeCodeSettingEditorWidget(language="en", targetScope=Scope.PROJECT)
    qtbot.addWidget(w)
    assert not _visible(w, "askUserQuestionTimeout") and not w.isKeyExposed(SettingKey.askUserQuestionTimeout)
    assert _visible(w, "model")
    w.setTargetScope(Scope.USER | Scope.PROJECT)                               # 둘 중 하나라도 효력이 있으면 표시
    assert _visible(w, "askUserQuestionTimeout")


def test_any_file_shows_managed_but_never_global_config(qtbot):
    w = QClaudeCodeSettingEditorWidget(language="en", targetScope=Scope.ANY_FILE)
    qtbot.addWidget(w)
    assert _visible(w, "claudeMd") and not w.rowFor("sandbox").editor.rows["bwrapPath"].isHidden()
    assert not _visible(w, "autoConnectIde")
    for bad in (Scope.GLOBAL_CONFIG, Scope.NONE, Scope.USER | Scope.GLOBAL_CONFIG):
        with pytest.raises(ValueError):
            w.setTargetScope(bad)


def test_nav_counts_follow_target_scope(qtbot):
    w = QClaudeCodeSettingEditorWidget(language="en", targetScope=Scope.ANY_FILE)
    qtbot.addWidget(w)
    idx = w.categoryIds().index("admin")
    w.setSettings({"requiredMinimumVersion": "2.0.0"})
    w._flush_change()
    assert "(1/" in w._nav.item(idx).text()
    w.setTargetScope(Scope.USER)
    assert w._nav.item(idx).text().startswith("Updates") and "(1/" not in w._nav.item(idx).text()


def test_save_file_keeps_values_of_hidden_keys(qtbot, tmp_path):
    doc = {"model": "opus", "claudeMd": "조직 규칙", "autoConnectIde": True, "availableModelsMatch": "exact",
           "sandbox": {"bwrapPath": "/usr/bin/bwrap"}, "zzzCustom": {"x": 1}, "env": {"MY_VAR": "1"}}
    src = tmp_path / "in.json"
    src.write_text(json.dumps(doc, ensure_ascii=False), "utf-8")
    w = QClaudeCodeSettingEditorWidget(language="en", targetVersion="2.1.200")         # USER, 2.1.200
    qtbot.addWidget(w)
    w.loadFile(src)
    w.setSettingValue(SettingKey.model, "sonnet")
    text = w.saveFile(tmp_path / "out.json").read_text("utf-8")
    assert json.loads(text) == dict(doc, model="sonnet")                       # 스코프·버전 밖·미지 키도 그대로
    assert text.endswith("\n") and "조직 규칙" in text


# --------------------------------------------------------------------------- 위젯: 버전
def test_target_version_hides_keys_added_later_or_removed_earlier(qtbot):
    w = QClaudeCodeSettingEditorWidget(language="en", targetScope=Scope.ANY_FILE, targetVersion="2.1.282")
    qtbot.addWidget(w)
    assert w.targetVersion() == "2.1.282"
    assert not _visible(w, "availableModelsMatch")                            # since 2.1.283
    assert not _visible(w, "taskOutputMaxChars") and _visible(w, "model")     # 2.1.277 에서 제거
    w.setTargetVersion("2.1.283")
    assert _visible(w, "availableModelsMatch")
    w.setTargetVersion("2.1.270")                                             # since 2.1.261 ~ removed 2.1.277
    assert _visible(w, "taskOutputMaxChars") and not _visible(w, "availableModelsMatch")
    w.setTargetVersion("2.1.260")
    assert not _visible(w, "taskOutputMaxChars")
    w.setTargetVersion(None)
    assert _visible(w, "availableModelsMatch") and _visible(w, "taskOutputMaxChars")
    with pytest.raises(ValueError):
        w.setTargetVersion("latest")


def test_scope_and_version_filters_block_api_bypass(qtbot):
    w = QClaudeCodeSettingEditorWidget(language="en")                          # USER
    qtbot.addWidget(w)
    with pytest.raises(HiddenKeyError):
        w.setSettingValue(SettingKey.availableModelsMatch, "exact")
    with pytest.raises(HiddenKeyError) as e:
        w.setSettingValue(SettingKey.sandbox, {"enabled": True, "bwrapPath": "/x"})
    assert e.value.keys == ["sandbox.bwrapPath"]
    w.setSettingValue(SettingKey.sandbox, {"enabled": True})
    w.setTargetVersion("2.1.200")
    with pytest.raises(HiddenKeyError):
        w.UpdateSetting({"maxEffortLevel": "high"})                             # since 2.1.267
    assert w.settings() == {"sandbox": {"enabled": True}}


# --------------------------------------------------------------------------- 표시·편집기
def _badge_texts(row):
    return [lb.text() for lb in row.findChildren(QtWidgets.QLabel)]


def test_rows_show_scope_since_and_lifecycle_badges(qtbot):
    w = QClaudeCodeSettingEditorWidget(language="en", targetScope=Scope.ANY_FILE)
    qtbot.addWidget(w)
    texts = _badge_texts(w.rowFor("availableModelsMatch"))
    assert "managed" in texts and "v2.1.283+" in texts
    assert "user · managed" in _badge_texts(w.rowFor("askUserQuestionTimeout"))
    assert "deprecated" in _badge_texts(w.rowFor("voiceEnabled"))
    assert "removed v2.1.277" in _badge_texts(w.rowFor("taskOutputMaxChars"))


def test_docs_only_keys_get_editors(qtbot):
    w = QClaudeCodeSettingEditorWidget(language="en", targetScope=Scope.ANY_FILE)
    qtbot.addWidget(w)
    assert isinstance(w.rowFor("maxEffortLevel").editor, EnumEditor)
    assert isinstance(w.rowFor("modelPicker").editor, ObjectEditor)            # overrides 의 스키마
    assert "defaultEnvironmentId" in w.rowFor("remote").editor.rows             # 중첩 키만 문서에 있던 객체
    assert isinstance(w.rowFor("timeFormat").editor, StringEditor)              # 프리셋 + strftime 자유 입력
    w.UpdateSetting({"modelPicker": {"options": [{"model": "opus", "label": "Opus"}]}, "timeFormat": "%H:%M"})
    assert w.settings() == {"modelPicker": {"options": [{"model": "opus", "label": "Opus"}]}, "timeFormat": "%H:%M"}
