import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTEST_QT_API", "pyside6")
os.environ.setdefault("QCCSE_LANG", "en")  # 시스템 로케일과 무관하게 영어 소스로 테스트
