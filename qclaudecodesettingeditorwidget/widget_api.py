"""QClaudeCodeSettingEditorWidget 의 공개 데이터 API 와 노출 정책(우회 방지).

값의 실제 보관처(구축된 PropertyRow / 미구축 페이지의 _pending / 노출되지 않은 키의 _passthrough / env 편집기)를
widget.py 의 저수준 헬퍼(_key_value, _set_key_value, _env_dict, _set_env_dict …)로 추상화하고,
이 믹스인은 그 위에서 settings()/setSettings()/UpdateSetting()/UpdateEnv() 와 정책 검사를 구현한다.

두 가지 검사가 있다.
- 노출 정책(HiddenKeyError): 이 위젯에 노출되지 않은 키를 API 로 바꾸는 것은 **거부**한다(우회 방지).
- 스키마 검증(SettingValidationWarning): 값의 문제는 **막지 않고** 파이썬 경고로 알린 뒤 그대로 적용·보존한다.
  API 로 값을 넣을 때·저장할 때는 적용 **전에** 경고하므로, 호출하는 앱이
  warnings.simplefilter("error", SettingValidationWarning) 를 켜면 문제 있는 값은 적용되지 않는다(엄격 모드).
  파일·initialSettings 같은 신뢰 소스는 일단 싣고 나서 경고한다(고칠 수 있게 화면에 올리는 것이 먼저).
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any

from .categories import Category
from .constants import ENV_KEY
from .i18n import tr
from .keys import EnvVar, SettingKey, setting_info
from .schema import JsonSchema, find_inapplicable_paths, load_schema, prune_inapplicable
from .spec import Version
from .validation import Issue, SettingValidationWarning, validate_settings

_MISSING = object()


def settings_for_version(data: dict[str, Any], version: Version | str,
                         schema: JsonSchema | None = None) -> dict[str, Any]:
    """data 에서 그 Claude Code 버전("2.1.250", Version, LATEST_VERSION)에 있는 키만 남긴 사본.

    최상위 키와 중첩 경로(sandbox.bwrapPath 등)를 since/removed 로 거른다. 버전 메타데이터가 없는 키
    (스키마 밖 키·env 변수 포함)는 남기고, deprecated 키도 그 버전에서 아직 동작하므로 남긴다.
    schema 가 None 이면 번들 스키마. 버전 형식이 틀리면 ValueError.
    """
    v = Version.parse(version)
    schema = load_schema() if schema is None else schema
    props = schema.get("properties", {})

    def available(path: str) -> bool:
        info = setting_info(path)
        return info is None or info.available_in(v)

    out: dict[str, Any] = {}
    for key, value in data.items():
        if available(key):
            prop = props.get(key)
            out[key] = value if prop is None else prune_inapplicable(prop, value, schema, available, key)[0]
    return out


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
    def settings(self, version: Version | str | None = None) -> dict[str, Any]:
        """현재 설정을 dict 로. 설정된 키만 포함하며 키 순서는 스키마 순서. 노출되지 않은 키의 보존값도 포함.

        version 을 주면 그 Claude Code 버전에 있는 키만 담는다(settings_for_version, LATEST_VERSION = 번들 기준 최신).
        편집 대상 버전(targetVersion)과는 별개이며 None 이면 거르지 않는다.
        """
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
        return out if version is None else settings_for_version(out, version, self._schema)

    def setSettings(self, data: dict[str, Any] | None, *, trusted: bool = False) -> None:
        """설정 전체를 교체한다. 스키마 문제는 SettingValidationWarning 으로 알리고 값은 그대로 싣는다.

        trusted=False(기본): 이 위젯에 노출되지 않은 키(숨긴 카테고리·대상 스코프/버전 밖·env 페이지 없음 등)는
        현재 보존값과 동일할 때만 허용하고, 바뀌었으면 HiddenKeyError 를 낸다(우회 방지). 경고는 적용 전에 낸다.
        trusted=True: 파일 등 신뢰 소스에서 읽은 문서. 노출되지 않은 키는 읽기 전용으로 보존하고, 경고는 적용 후에 낸다.
        """
        self._set_document(data, trusted)

    def _set_document(self, data: dict[str, Any] | None, trusted: bool) -> None:
        """setSettings 본체. 공개 진입점(setSettings·SetSetting·loadFile·생성자)이 바로 부르므로 경고는 그 호출자를 가리킨다."""
        data = dict(data or {})
        issues = validate_settings(data, self._schema)
        if not trusted:
            self._check_document(data)
            self._warn(issues, stacklevel=4)
        self._load_document(data)
        if trusted:
            self._warn(issues, stacklevel=4)

    def _load_document(self, data: dict[str, Any]) -> None:
        """정책 검사·경고 없이 문서 교체(언어 전환·clear 등 내부용)."""
        self._replace_all(data)
        self._on_changed()

    @staticmethod
    def _warn(issues: list[Issue], stacklevel: int = 3) -> None:
        """stacklevel 3 = _warn 을 부른 공개 메서드의 호출자(사용자 코드)."""
        if issues:
            warnings.warn(SettingValidationWarning(issues), stacklevel=stacklevel)

    def GetSetting(self, indent: int | None = 2, *, version: Version | str | None = None) -> str:
        """설정을 JSON 문자열로 반환. version 은 settings() 와 같다(그 버전에 있는 키만)."""
        return json.dumps(self.settings(version), indent=indent, ensure_ascii=False)

    def GetSettingJsonl(self, *, version: Version | str | None = None) -> str:
        """설정을 한 줄 JSON(JSONL 레코드 한 줄)으로 반환. 개행 없음. version 은 settings() 와 같다."""
        return json.dumps(self.settings(version), ensure_ascii=False, separators=(",", ":"))

    def SetSetting(self, text: str, *, trusted: bool = False) -> None:
        """JSON 문자열에서 설정 로드. 파싱 실패 시 ValueError, 노출되지 않은 키 변경 시 HiddenKeyError.
        스키마 문제는 SettingValidationWarning(값은 그대로 싣는다)."""
        self._set_document(self._parse_document(text), trusted)

    @staticmethod
    def _parse_document(text: str) -> dict[str, Any]:
        data = json.loads(text) if text.strip() else {}
        if not isinstance(data, dict):
            raise ValueError(tr("Top level of settings JSON must be an object"))
        return data

    def clear(self) -> None:
        """노출된 키를 모두 해제한다. 노출되지 않은 키의 보존값은 그대로 둔다."""
        keep = {k: self._current_for_compare(k) for k in self._all_hidden_current_keys()}
        self._load_document(keep)

    def loadFile(self, path: str | Path) -> None:
        """파일(신뢰 소스)에서 로드. 노출되지 않은 키는 읽기 전용으로 보존된다.
        스키마 문제가 있어도 그대로 싣고 SettingValidationWarning 으로 알린다."""
        p = Path(path)
        self._set_document(self._parse_document(p.read_text("utf-8")), trusted=True)
        self._file_path = p
        self.fileLoaded.emit(str(p))

    def saveFile(self, path: str | Path | None = None, *, version: Version | str | None = None) -> Path:
        """설정 파일로 저장(들여쓰기 2, 끝 줄바꿈). path 가 None 이면 마지막으로 읽거나 쓴 경로.

        version 을 주면 그 Claude Code 버전에 있는 키만 쓴다("2.1.250", LATEST_VERSION).
        None 이면 숨긴 키의 보존값까지 그대로 쓴다.
        스키마 문제가 있어도 저장하며, 쓰기 전에 SettingValidationWarning 으로 알린다(엄격 모드면 쓰지 않는다).
        """
        p = Path(path) if path is not None else self._file_path
        if p is None:
            raise ValueError(tr("No save path"))
        data = self.settings(version)
        self._warn(validate_settings(data, self._schema))
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", "utf-8")
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
        """최상위 설정 키 하나를 설정. value 가 None 이면 해제. 노출되지 않은 키는 HiddenKeyError.
        스키마 문제는 적용 전에 SettingValidationWarning 으로 알리고 값은 그대로 적용한다."""
        k = SettingKey.coerce(key)
        self._check_value(k, value)
        if k == ENV_KEY and value is not None:
            if not isinstance(value, dict):
                raise ValueError(tr("env must be an object or null"))
            value = self._env_changes(value)
        self._warn(self._value_issues({k: value}))
        self._apply_value(k, value)

    def _value_issues(self, values: dict[str, Any]) -> list[Issue]:
        """API 로 넣으려는 값들의 스키마 문제(None = 해제는 제외, env 안의 None 도 제외)."""
        check = {k: ({n: x for n, x in v.items() if x is not None} if k == ENV_KEY and isinstance(v, dict) else v)
                 for k, v in values.items() if v is not None}
        return validate_settings(check, self._schema)

    @staticmethod
    def _env_changes(changes: dict[str, Any]) -> dict[str, Any]:
        """env API 의 편의 변환: 숫자(불리언 제외)는 손실 없이 문자열로(5 → "5"). 불리언·객체 등은 그대로 두고
        검증 경고로 알린다("true"/"1" 중 무엇이 맞는지 위젯이 정할 수 없다)."""
        return {EnvVar.coerce(n): str(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v
                for n, v in changes.items()}

    def _apply_value(self, k: str, value: Any) -> None:
        """검사·경고 없이 최상위 키 하나를 적용(env 는 전체 교체)."""
        if k == ENV_KEY:
            self._set_env_dict(dict(value or {}))
        else:
            self._set_key_value(k, value)
        self._on_changed()

    def unsetSetting(self, key: str | SettingKey) -> None:
        self.setSettingValue(key, None)

    def envValue(self, name: str | EnvVar, default: Any = None) -> Any:
        """env 변수 하나의 값(보통 문자열). 미설정이면 default."""
        return self._env_dict().get(EnvVar.coerce(name), default)

    def setEnvValue(self, name: str | EnvVar, value: Any) -> None:
        """env 변수 하나를 설정. value 가 None 이면 해제. env 페이지가 없으면 HiddenKeyError.
        숫자는 문자열로 저장하고, 그 밖의 문자열이 아닌 값은 그대로 싣되 SettingValidationWarning 으로 알린다."""
        self._update_env({EnvVar.coerce(name): value})

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
        아무것도 적용하지 않고 HiddenKeyError. 스키마 문제는 적용 전에 한 번 SettingValidationWarning 으로 알리고
        그대로 적용한다. 갱신 후 settings() 를 돌려준다.
        """
        obj = {SettingKey.coerce(key): value for key, value in self._parse_object(data).items()}
        bad: list[str] = []
        for k, value in obj.items():  # 부분 적용을 막기 위해 먼저 전부 검사
            if k == ENV_KEY and value is not None:
                if not isinstance(value, dict):
                    raise ValueError(tr("env must be an object or null"))
                obj[k] = value = self._env_changes(value)
            try:
                self._check_value(k, value)
            except HiddenKeyError as e:
                bad.extend(e.keys)
        if bad:
            raise HiddenKeyError(sorted(set(bad)))
        self._warn(self._value_issues(obj))
        for k, value in obj.items():
            if k == ENV_KEY and value is not None:
                self._set_env_dict(self._merged_env(value))
                self._on_changed()
            else:
                self._apply_value(k, value)
        return self.settings()

    def UpdateEnv(self, data: str | dict[str, Any], *, replace: dict[str, Any] | None = None) -> dict[str, Any]:
        """JSON(문자열 또는 dict)의 환경변수들을 현재 env 에 **병합**한다.

        {"API_TIMEOUT_MS": "1200000"} 처럼 하나만 넘겨도 되고, 값이 null 이면 해제된다.
        replace 를 주면 병합 대신 env 전체를 그 dict 로 바꾼다. env 페이지가 없으면 HiddenKeyError.
        숫자는 문자열로 저장한다(5 → "5"). 불리언·객체 같은 값과 잘못된 변수 이름은 바꾸지 않고 싣되, 적용 전에
        SettingValidationWarning 으로 알린다. 갱신 후 env dict 를 돌려준다.
        """
        return self._update_env(self._parse_object(data), replace)

    def _update_env(self, obj: dict[str, Any], replace: dict[str, Any] | None = None) -> dict[str, Any]:
        """UpdateEnv 본체. 공개 진입점(UpdateEnv·setEnvValue)이 바로 부르므로 경고는 그 호출자를 가리킨다."""
        if not self._env_enabled:
            raise HiddenKeyError([str(ENV_KEY)])
        if replace is not None:
            if not isinstance(replace, dict):
                raise ValueError(tr("env must be an object or null"))
            obj = replace
        obj = self._env_changes(obj)
        self._warn(self._value_issues({ENV_KEY: obj}), stacklevel=4)
        merged = self._merged_env(obj, base={} if replace is not None else None)
        self._set_env_dict(merged)
        self._on_changed()
        return dict(merged)

    def _merged_env(self, changes: dict[str, Any], base: dict[str, Any] | None = None) -> dict[str, Any]:
        """현재 env(또는 base)에 changes 를 병합한 사본. 값이 None 이면 해제."""
        merged = dict(self._env_dict() if base is None else base)
        for name, value in changes.items():
            n = EnvVar.coerce(name)
            if value is None:
                merged.pop(n, None)
            else:
                merged[n] = value
        return merged

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
            return dict(env) if env else self._passthrough.get(ENV_KEY, _MISSING)
        return self._key_value(k)

    def _all_hidden_current_keys(self) -> list[str]:
        """설정되어 있지만 노출되지 않은 키(보존값) 목록."""
        keys = [k for k in self._set_keys() if not self.isKeyExposed(k)]
        if not self._env_enabled and self._env_dict():
            keys.append(str(ENV_KEY))
        return keys
