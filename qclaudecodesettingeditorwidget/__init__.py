"""QClaudeCodeSettingEditorWidget — Claude Code settings.json 편집용 PySide6 위젯.

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
from .categories import Category
from .schema import EnvVarInfo, load_env_registry, load_schema
from .widget import QClaudeCodeSettingEditorWidget

__version__ = "0.1.0"
__all__ = ["QClaudeCodeSettingEditorWidget", "Category", "EnvVarInfo", "load_env_registry", "load_schema", "__version__"]
