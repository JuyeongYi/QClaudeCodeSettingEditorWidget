"""QClaudeCodeSettingEditorWidget — Claude Code settings.json 편집용 PySide6 위젯.

패키지 버전은 번들 메타데이터를 생성한 Claude Code 버전과 같다(_version.py).

사용 예::

    from PySide6 import QtWidgets
    from qclaudecodesettingeditorwidget import QClaudeCodeSettingEditorWidget

    app = QtWidgets.QApplication([])
    w = QClaudeCodeSettingEditorWidget()
    w.SetSetting('{"model": "opus", "env": {"API_TIMEOUT_MS": "1200000"}}')
    w.show()
    app.exec()
    print(w.GetSetting())        # 들여쓰기된 JSON
    print(w.GetSettingJsonl())   # 한 줄 JSON
"""
from ._version import __version__
from .categories import Category
from .constants import JsonType, Precedence, Scope, Topic
from .keys import NESTED_SETTINGS, EnvVar, KeyEnum, SettingKey, setting_info
from .schema import EnvVarInfo, load_env_registry, load_schema
from .spec import SettingInfo, Version
from .widget import HiddenKeyError, QClaudeCodeSettingEditorWidget

__all__ = ["QClaudeCodeSettingEditorWidget", "HiddenKeyError", "Category", "Scope", "JsonType", "Topic", "Precedence",
           "Version", "SettingKey", "SettingInfo",
           "NESTED_SETTINGS", "setting_info", "EnvVar", "KeyEnum", "EnvVarInfo", "load_env_registry", "load_schema",
           "__version__"]
