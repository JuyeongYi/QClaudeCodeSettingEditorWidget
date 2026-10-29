import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTEST_QT_API", "pyside6")

from qclaudecodesettingeditorwidget.constants import ENV_LANG, SOURCE_LANG  # noqa: E402

os.environ.setdefault(ENV_LANG, SOURCE_LANG)  # 시스템 로케일과 무관하게 영어 소스로 테스트
