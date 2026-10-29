"""QClaudeCodeSettingEditorWidget 의 공개 데이터 API 와 노출 정책(우회 방지).

값의 실제 보관처(구축된 PropertyRow / 미구축 페이지의 _pending / 노출되지 않은 키의 _passthrough / env 편집기)를
widget.py 의 저수준 헬퍼(_key_value, _set_key_value, _env_dict, _set_env_dict …)로 추상화하고,
이 믹스인은 그 위에서 settings()/setSettings()/UpdateSetting()/UpdateEnv() 와 정책 검사를 구현한다.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .categories import Category
from .constants import ENV_KEY
from .i18n import tr
from .keys import EnvVar, SettingKey
from .schema import find_inapplicable_paths

_MISSING = object()


class HiddenKeyError(ValueError):
    """이 위젯에 노출되지 않은 키(숨긴 카테고리·대상 스코프/버전 밖·env 페이지 없음 등)를 API 로 바꾸려 할 때."""

    def __init__(self, keys: list[str]):
        self.keys = list(keys)
        super().__init__(tr("Keys not exposed in this widget cannot be changed: {keys}", keys=", ".join(self.keys)))


class SettingsApiMixin:
    """widget.py 가 제공해야 하는 것: _schema, _categories, _env_enabled, _page_by_key(키→페이지),
    _meta(키→KeyMeta), _passthrough, _key_value(k), _set_key_value(k, v), _env_dict(), _set_env_dict(d),
    _set_keys(), _on_changed(), isKeyApplicable(path), _file_path, fileLoaded/fileSaved 시그널."""

    # ------------------------------------------------------------------ 전체 읽기/쓰기
    def settings(self) -> dict[str, Any]:
        """현재 설정을 dict 로. 설정된 키만 포함하며 키 순서는 스키마 순서. 노출되지 않은 키의 보존값도 포함."""
        out: dict[str, Any] = {}
        for key in self._schema.get("properties", {}):
            if key == ENV_KEY:
                env = self._env_dict()
                if env:
                    out[ENV_KEY] = dict(env)
                continue
            v = self._key_value(key)
            if v is not _MISSING:
                out[key] = v
        for k, v in self._passthrough.items():
            out.setdefault(k, v)
        return out

    def setSettings(self, data: dict[str, Any] | None, *, trusted: bool = False) -> None:
        """설정 전체를 교체한다.

        trusted=False(기본): 이 위젯에 노출되지 않은 키(숨긴 카테고리·대상 스코프/버전 밖·env 페이지 없음 등)는
        현재 보존값과 동일할 때만 허용하고, 바뀌었으면 HiddenKeyError 를 낸다(우회 방지).
        trusted=True: 파일 등 신뢰 소스에서 읽은 문서. 노출되지 않은 키는 읽기 전용으로 보존한다.
        """
        data = dict(data or {})
        if not trusted:
            self._check_document(data)
        self._replace_all(data)
        self._on_changed()

    def GetSetting(self, indent: int | None = 2) -> str:
        """설정을 JSON 문자열로 반환."""
        return json.dumps(self.settings(), indent=indent, ensure_ascii=False)

    def GetSettingJsonl(self) -> str:
        """설정을 한 줄 JSON(JSONL 레코드 한 줄)으로 반환. 개행 없음."""
        return json.dumps(self.settings(), ensure_ascii=False, separators=(",", ":"))

    def SetSetting(self, text: str, *, trusted: bool = False) -> None:
        """JSON 문자열에서 설정 로드. 파싱 실패 시 ValueError, 노출되지 않은 키 변경 시 HiddenKeyError."""
        data = json.loads(text) if text.strip() else {}
        if not isinstance(data, dict):
            raise ValueError(tr("Top level of settings JSON must be an object"))
        self.setSettings(data, trusted=trusted)

    def clear(self) -> None:
        """노출된 키를 모두 해제한다. 노출되지 않은 키의 보존값은 그대로 둔다."""
        keep = {k: self._key_value(k) for k in self._all_hidden_current_keys()}
        self.setSettings(keep, trusted=True)

    def loadFile(self, path: str | Path) -> None:
        """파일(신뢰 소스)에서 로드. 노출되지 않은 키는 읽기 전용으로 보존된다."""
        p = Path(path)
        self.SetSetting(p.read_text("utf-8"), trusted=True)
        self._file_path = p
        self.fileLoaded.emit(str(p))

    def saveFile(self, path: str | Path | None = None) -> Path:
        p = Path(path) if path is not None else self._file_path
        if p is None:
            raise ValueError(tr("No save path"))
        p.write_text(self.GetSetting() + "\n", "utf-8")
        self._file_path = p
        self.fileSaved.emit(str(p))
        return p

    def filePath(self) -> Path | None:
        return self._file_path

    # ------------------------------------------------------------------ 단건 접근 (enum 키)
    def settingValue(self, key: str | SettingKey, default: Any = None) -> Any:
        """최상위 설정 키 하나의 값. 미설정이면 default. env 는 envValue()/UpdateEnv() 를 쓴다."""
        k = SettingKey.coerce(key)
        if k == ENV_KEY:
            env = self._env_dict()
            return dict(env) if env else default
        v = self._key_value(k)
        return default if v is _MISSING else v

    def setSettingValue(self, key: str | SettingKey, value: Any) -> None:
        """최상위 설정 키 하나를 설정. value 가 None 이면 해제. 노출되지 않은 키는 HiddenKeyError."""
        k = SettingKey.coerce(key)
        self._check_value(k, value)
        if k == ENV_KEY:
            self.UpdateEnv({}, replace=value if value is not None else {})
            return
        self._set_key_value(k, value)
        self._on_changed()

    def unsetSetting(self, key: str | SettingKey) -> None:
        self.setSettingValue(key, None)

    def envValue(self, name: str | EnvVar, default: str | None = None) -> str | None:
        """env 변수 하나의 값. 미설정이면 default."""
        return self._env_dict().get(EnvVar.coerce(name), default)

    def setEnvValue(self, name: str | EnvVar, value: str | None) -> None:
        """env 변수 하나를 설정. value 가 None 이면 해제. env 페이지가 없으면 HiddenKeyError."""
        self.UpdateEnv({EnvVar.coerce(name): value})

    # ------------------------------------------------------------------ JSON 병합 갱신
    @staticmethod
    def _parse_object(data: str | dict[str, Any]) -> dict[str, Any]:
        obj = json.loads(data) if isinstance(data, str) else data
        if not isinstance(obj, dict):
            raise ValueError(tr("Top level of settings JSON must be an object"))
        return obj

    def UpdateSetting(self, data: str | dict[str, Any]) -> dict[str, Any]:
        """JSON(문자열 또는 dict)의 최상위 키들을 현재 설정에 **병합**한다.

        {"model": "opus"} 처럼 키 하나만 넘겨도 되고, 값이 null 인 키는 해제된다.
        "env" 키가 있으면 UpdateEnv 와 같은 병합 규칙을 적용한다. 노출되지 않은 키가 하나라도 있으면
        아무것도 적용하지 않고 HiddenKeyError. 갱신 후 settings() 를 돌려준다.
        """
        obj = {SettingKey.coerce(key): value for key, value in self._parse_object(data).items()}
        bad: list[str] = []
        for k, value in obj.items():  # 부분 적용을 막기 위해 먼저 전부 검사
            if k == ENV_KEY and value is not None and not isinstance(value, dict):
                raise ValueError("env must be an object or null")
            try:
                self._check_value(k, value)
            except HiddenKeyError as e:
                bad.extend(e.keys)
        if bad:
            raise HiddenKeyError(sorted(set(bad)))
        for k, value in obj.items():
            if k == ENV_KEY:
                if value is None:
                    self.UpdateEnv({}, replace={})
                else:
                    self.UpdateEnv(value)
            else:
                self.setSettingValue(k, value)
        return self.settings()

    def UpdateEnv(self, data: str | dict[str, Any], *, replace: dict[str, Any] | None = None) -> dict[str, str]:
        """JSON(문자열 또는 dict)의 환경변수들을 현재 env 에 **병합**한다.

        {"API_TIMEOUT_MS": "1200000"} 처럼 하나만 넘겨도 되고, 값이 null 이면 해제된다.
        replace 를 주면 병합 대신 env 전체를 그 dict 로 바꾼다. env 페이지가 없으면 HiddenKeyError.
        갱신 후 env dict 를 돌려준다.
        """
        obj = self._parse_object(data)
        if not self._env_enabled:
            raise HiddenKeyError([str(ENV_KEY)])
        if replace is not None:
            if not isinstance(replace, dict):
                raise ValueError("env must be an object")
            obj = replace
            merged: dict[str, str] = {}
        else:
            merged = dict(self._env_dict())
        for name, value in obj.items():
            n = EnvVar.coerce(name)
            if value is None:
                merged.pop(n, None)
            else:
                merged[n] = str(value)
        self._set_env_dict(merged)
        self._on_changed()
        return dict(merged)

    # ------------------------------------------------------------------ 노출 정책(우회 방지)
    def isKeyExposed(self, key: str | SettingKey) -> bool:
        """이 위젯에서 편집 가능한(노출된) 최상위 키인지."""
        k = SettingKey.coerce(key)
        if k == ENV_KEY:
            return self._env_enabled
        if k in self._page_by_key:
            return self.isKeyApplicable(k)
        if k in self._schema.get("properties", {}):
            return False  # 숨긴 카테고리
        return bool(Category.OTHER & self._categories)  # 스키마 밖 키는 OTHER 가 노출될 때만

    def inapplicableKeys(self) -> list[str]:
        """노출 카테고리에 있지만 대상 스코프·버전에서 효력이 없어 숨긴 최상위 키."""
        return [k for k in self._page_by_key if not self.isKeyApplicable(k)]

    def _check_value(self, k: str, value: Any) -> None:
        """단건 변경 허용 검사: 키 노출 여부 + 값 안의 중첩 경로(대상 스코프·버전 밖이면 거부)."""
        if not self.isKeyExposed(k):
            raise HiddenKeyError([k])
        if k != ENV_KEY and value is not None:
            prop = self._schema.get("properties", {}).get(k)
            if prop is not None:
                paths = find_inapplicable_paths(prop, value, self._schema, self.isKeyApplicable, k)
                if paths:
                    raise HiddenKeyError(paths)

    def _check_document(self, data: dict[str, Any]) -> None:
        """전체 문서 교체 허용 검사: 노출되지 않은 키는 현재 보존값과 같아야 한다."""
        bad: list[str] = []
        for k, v in data.items():
            if self.isKeyExposed(k):
                try:
                    self._check_value(k, v)
                except HiddenKeyError as e:
                    bad.extend(e.keys)
            elif self._current_for_compare(k) != v:
                bad.append(k)
        for k in self._all_hidden_current_keys():
            if k not in data:
                bad.append(k)  # 숨긴 키 제거도 변경이다
        if bad:
            raise HiddenKeyError(sorted(set(bad)))

    def _current_for_compare(self, k: str) -> Any:
        if k == ENV_KEY:
            env = self._env_dict()
            return dict(env) if env else _MISSING
        return self._key_value(k)

    def _all_hidden_current_keys(self) -> list[str]:
        """설정되어 있지만 노출되지 않은 키(보존값) 목록."""
        keys = [k for k in self._set_keys() if not self.isKeyExposed(k)]
        if not self._env_enabled and self._env_dict():
            keys.append(str(ENV_KEY))
        return keys
