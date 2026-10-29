"""tools 가 쓰는 패키지 모듈(constants, spec, schema) 로더.

패키지 __init__(Qt)·keys.py 를 거치지 않는다 — keys.py 가 깨져 있어도 재생성할 수 있게.
실제 패키지 이름 대신 스텁 패키지 아래로 올려 모듈 간 상대 임포트(spec → .constants)도 동작한다.
"""
from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from typing import TYPE_CHECKING

__all__ = ["PKG", "ENV_KEY", "JsonType", "Precedence", "Scope", "Topic", "Version", "constants", "schema", "spec",
           "load_pkg_module"]

PKG = Path(__file__).resolve().parents[2] / "qclaudecodesettingeditorwidget"
_STUB = "_qccse"


def load_pkg_module(name: str):
    if _STUB not in sys.modules:
        stub = types.ModuleType(_STUB)
        stub.__path__ = [str(PKG)]
        sys.modules[_STUB] = stub
    return importlib.import_module(f"{_STUB}.{name}")


constants = load_pkg_module("constants")
spec = load_pkg_module("spec")
schema = load_pkg_module("schema")

ENV_KEY = constants.ENV_KEY
if TYPE_CHECKING:  # 타입 검사기에는 실제 패키지의 클래스로 보이게
    from qclaudecodesettingeditorwidget.constants import JsonType, Precedence, Scope, Topic
    from qclaudecodesettingeditorwidget.spec import Version
else:
    JsonType, Precedence, Scope, Topic = constants.JsonType, constants.Precedence, constants.Scope, constants.Topic
    Version = spec.Version
