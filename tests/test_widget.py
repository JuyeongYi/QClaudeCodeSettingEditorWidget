"""위젯 통합 테스트(offscreen Qt)."""
import json

import pytest

from qclaudecodesettingeditorwidget import QClaudeCodeSettingEditorWidget, load_schema
from qclaudecodesettingeditorwidget.editors import (
    AnyOfEditor,
    CheckListEditor,
    DictEditor,
    ListEditor,
    NullableEditor,
    ObjectEditor,
    RawJsonEditor,
    StringEditor,
    StringListEditor,
)

SAMPLE = {
    "$schema": "https://www.schemastore.org/claude-code-settings.json",
    "model": "opus",
    "effortLevel": "high",
    "fastMode": True,
    "cleanupPeriodDays": 14,
    "feedbackSurveyRate": 0.25,
    "theme": "custom:solarized",
    "teammateDefaultModel": None,
    "strictPluginOnlyCustomization": ["skills", "hooks"],
    "availableModels": ["opus", "sonnet"],
    "modelOverrides": {"claude-opus-4-6": "arn:aws:bedrock:us-east-2:1:x"},
    "skillOverrides": {"deploy": "off"},
    "permissions": {
        "allow": ["Bash(git *)", "Read(*)"],
        "deny": ["Read(./.env)"],
        "defaultMode": "acceptEdits",
        "additionalDirectories": ["../shared"],
    },
    "hooks": {
        "PreToolUse": [
            {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo hi", "timeout": 5}]},
            {"hooks": [{"type": "command", "command": "pwsh -c x", "shell": "powershell", "async": True}]},
        ],
        "Stop": [{"hooks": [{"type": "command", "command": "notify"}]}],
    },
    "allowedMcpServers": [
        {"serverName": "github"},
        {"serverCommand": ["npx", "-y", "server"]},
        {"serverUrl": "https://*.example.com/*"},
    ],
    "enabledPlugins": {"formatter@anthropic-tools": True, "lint@x": ["a", "b"]},
    "extraKnownMarketplaces": {
        "corp": {"source": {"source": "github", "repo": "corp/plugins", "ref": "main"}},
        "raw": {"source": {"source": "url", "url": "https://example.com/marketplace.json"}},
    },
    "sandbox": {
        "enabled": True,
        "network": {"allowedDomains": ["example.com"], "tlsTerminate": {"caCertPath": "/a", "caKeyPath": "/b"}},
        "filesystem": {"allowWrite": ["/tmp"]},
        "enabledPlatforms": ["linux", "wsl"],
        "ignoreViolations": {"*": ["/dev/null"]},
        "credentials": {"files": [{"path": "~/.aws/credentials", "mode": "deny"}], "allowPlaintextInject": False},
    },
    "statusLine": {"type": "command", "command": "~/bin/status.sh", "padding": 0},
    "policyHelper": {"path": "/x", "timeoutMs": 100, "refreshIntervalMs": 0},
    "sshConfigs": [{"id": "a", "name": "A", "sshHost": "user@host", "sshPort": 22}],
    "managedMcpServers": [{"type": "http", "url": "https://x", "toolPolicy": {"a": "allow"}}],
    "vimInsertModeRemaps": {"jj": "<Esc>"},
    "env": {
        "API_TIMEOUT_MS": "1200000",
        "CLAUDE_CODE_EFFORT_LEVEL": "max",
        "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
        "MY_CUSTOM_VAR": "hello",
        "ANTHROPIC_PROFILE": "work",
    },
    "someFutureKey": {"unknown": [1, 2, 3]},
}


@pytest.fixture
def widget(qtbot):
    w = QClaudeCodeSettingEditorWidget()
    qtbot.addWidget(w)
    return w


def test_every_schema_key_has_a_row(widget):
    schema = load_schema()
    keys = set(schema["properties"]) - {"env"}
    assert set(widget._rows) == keys
    assert widget.settings() == {}


def test_roundtrip_sample(widget):
    widget.setSettings(SAMPLE)
    out = widget.settings()
    assert out == SAMPLE
    assert json.loads(widget.GetSetting()) == SAMPLE
    jsonl = widget.GetSettingJsonl()
    assert "\n" not in jsonl and json.loads(jsonl) == SAMPLE


def test_set_setting_from_text_and_clear(widget):
    widget.SetSetting(json.dumps(SAMPLE))
    assert widget.settings()["model"] == "opus"
    widget.clear()
    assert widget.settings() == {}
    with pytest.raises(ValueError):
        widget.SetSetting("[1,2]")
    with pytest.raises(ValueError):
        widget.SetSetting("{not json")


def test_output_validates_against_schema(widget):
    jsonschema = pytest.importorskip("jsonschema")
    data = {k: v for k, v in SAMPLE.items() if k != "someFutureKey"}
    widget.setSettings(data)
    jsonschema.validate(widget.settings(), load_schema())


def test_editor_kinds_selected_by_factory(widget):
    assert isinstance(widget.rowFor("permissions").editor, ObjectEditor)
    assert isinstance(widget.rowFor("availableModels").editor, StringListEditor)
    assert isinstance(widget.rowFor("allowedMcpServers").editor, ListEditor)
    assert isinstance(widget.rowFor("modelOverrides").editor, DictEditor)
    assert isinstance(widget.rowFor("teammateDefaultModel").editor, NullableEditor)
    assert isinstance(widget.rowFor("strictPluginOnlyCustomization").editor, AnyOfEditor)
    assert isinstance(widget.rowFor("theme").editor, StringEditor)  # 문자열 anyOf → 제안 콤보
    assert isinstance(widget.rowFor("managedMcpServers").editor, ListEditor)
    sandbox = widget.rowFor("sandbox").editor
    assert isinstance(sandbox.rows["enabledPlatforms"].editor, CheckListEditor)
    assert isinstance(sandbox.rows["ignoreViolations"].editor, DictEditor)


def test_anyof_picks_matching_variant_and_falls_back_to_raw(widget):
    row = widget.rowFor("strictPluginOnlyCustomization")
    ed = row.editor
    row.setValue(True)
    assert ed.currentIndex() == 0 and row.value() is True
    row.setValue(["mcp"])
    assert ed.currentIndex() == 1 and row.value() == ["mcp"]
    row.setValue({"weird": 1})  # 어느 변형에도 안 맞음 → raw JSON 보존
    assert ed.currentIndex() == 2 and row.value() == {"weird": 1}
    assert isinstance(ed._ensure_editor(2), RawJsonEditor)


def test_editing_unchecked_row_auto_includes_it(widget, qtbot):
    row = widget.rowFor("model")
    assert not row.included()
    with qtbot.waitSignal(widget.settingChanged, timeout=1000):
        row.editor._line.setText("sonnet")
    assert row.included() and widget.settings() == {"model": "sonnet"}


def test_env_editor_set_and_unset(widget, qtbot):
    env = widget.envEditor()
    with qtbot.waitSignal(widget.settingChanged, timeout=1000):
        env.setVariable("CLAUDE_CODE_EFFORT_LEVEL", "low")
    env.setVariable("BRAND_NEW_VAR", "x")
    assert widget.settings()["env"] == {"CLAUDE_CODE_EFFORT_LEVEL": "low", "BRAND_NEW_VAR": "x"}
    env.setVariable("CLAUDE_CODE_EFFORT_LEVEL", None)
    assert widget.settings()["env"] == {"BRAND_NEW_VAR": "x"}
    env.setVariable("BRAND_NEW_VAR", None)
    assert "env" not in widget.settings()


def test_search_filter_hides_rows(widget):
    widget._search.setText("sandbox")
    assert widget.rowFor("sandbox").isVisible() or not widget.isVisible()  # offscreen: visibility flag
    page_counts = [p.applyFilter("sandbox", False) for p in widget._pages]
    assert sum(page_counts) >= 1
    assert all(p.applyFilter("zzz-no-such-key", False) == 0 for p in widget._pages)


def test_file_roundtrip(widget, tmp_path):
    widget.setSettings(SAMPLE)
    p = widget.saveFile(tmp_path / "settings.json")
    other = QClaudeCodeSettingEditorWidget()
    other.loadFile(p)
    assert other.settings() == SAMPLE
    assert other.filePath() == p
