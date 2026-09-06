"""QClaudeCodeSettingEditorWidget: Claude Code settings.json 전체를 편집하는 PySide6 위젯."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from . import i18n
from .categories import CATEGORY_TITLES, ENV_ID, ENV_KEY, JSON_ID, Category, categorize
from .editors import PropertyRow
from .env_editor import EnvEditor
from .i18n import tr
from .keys import EnvVar, SettingKey
from .schema import (
    EnvVarInfo,
    JsonSchema,
    find_managed_only_paths,
    load_env_registry,
    load_overlaps,
    load_schema,
    overlaps_by_env,
    resolve_ref,
)

MUTED = "color: #8a8a8a;"


class HiddenKeyError(ValueError):
    """이 위젯에 노출되지 않은 키(숨긴 카테고리·관리형 전용·env 페이지 없음 등)를 API 로 바꾸려 할 때."""

    def __init__(self, keys: list[str]):
        self.keys = list(keys)
        super().__init__(tr("Keys not exposed in this widget cannot be changed: {keys}", keys=", ".join(self.keys)))


_MISSING = object()


class _Page(QtWidgets.QWidget):
    """카테고리 한 페이지: PropertyRow 들을 세로로 쌓은 스크롤 영역."""

    def __init__(self, category_id: str, title: str, rows: list[PropertyRow], parent=None):
        super().__init__(parent)
        self.category_id = category_id
        self.title = title
        self.rows = rows
        body = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(body)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)
        heading = QtWidgets.QLabel(title)
        f = heading.font()
        f.setPointSize(f.pointSize() + 2)
        f.setBold(True)
        heading.setFont(f)
        v.addWidget(heading)
        self.empty_label = QtWidgets.QLabel(tr("No matches"))
        self.empty_label.setStyleSheet(MUTED)
        self.empty_label.hide()
        v.addWidget(self.empty_label)
        self._separators: list[QtWidgets.QFrame] = []
        for r in rows:
            v.addWidget(r)
            line = QtWidgets.QFrame()
            line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
            line.setStyleSheet("color: palette(midlight);")
            self._separators.append(line)
            v.addWidget(line)
        v.addStretch(1)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(scroll)

    def applyFilter(self, text: str, only_set: bool, show_managed: bool = True) -> int:
        shown = 0
        for r, sep in zip(self.rows, self._separators):
            ok = ((not text or r.matches(text)) and (not only_set or r.included())
                  and (show_managed or not r.managed_only))
            r.setVisible(ok)
            sep.setVisible(ok)
            shown += ok
        self.empty_label.setVisible(shown == 0)
        return shown


class QClaudeCodeSettingEditorWidget(QtWidgets.QWidget):
    """Claude Code settings.json 편집 위젯.

    공개 API
    - settings() / setSettings(dict)      : 파이썬 dict 로 읽기/쓰기
    - GetSetting(indent=2) -> str         : 설정을 JSON 문자열로
    - GetSettingJsonl() -> str            : 설정을 한 줄 JSON(JSONL 한 레코드)로
    - SetSetting(text: str)               : JSON 문자열로부터 로드
    - loadFile(path) / saveFile(path)     : 파일 입출력
    - clear()                             : 모든 키 해제
    - setLanguage(code) / language()      : 현지화 (locales/qccse_<code>.ts 또는 .qm 이 있으면 사용 가능)
    - settingChanged (Signal)             : 값이 바뀔 때마다
    """

    settingChanged = QtCore.Signal()
    fileLoaded = QtCore.Signal(str)
    fileSaved = QtCore.Signal(str)
    languageChanged = QtCore.Signal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None, *, schema: JsonSchema | None = None,
                 schema_path: str | Path | None = None, env_registry_path: str | Path | None = None,
                 env_registry: dict[str, EnvVarInfo] | None = None, language: str | None = None,
                 categories: Category = Category.ALL, overlaps: dict[str, list[dict[str, str]]] | None = None,
                 showManagedOnly: bool = False):
        """categories: 좌측에 노출할 카테고리 비트 플래그. 제외된 카테고리의 키는 편집할 수 없고,
        로드된 값은 _passthrough 로 보존되어 그대로 다시 내보낸다.
        showManagedOnly: 관리형(managed/policy) 설정에서만 유효한 키를 보여줄지. 기본 False(숨김).
        숨겨도 로드된 값은 보존되어 출력에 그대로 남는다."""
        super().__init__(parent)
        self._categories = Category(categories)
        self._show_managed = bool(showManagedOnly)
        self._schema: JsonSchema = schema if schema is not None else load_schema(schema_path)
        self._env_registry = (env_registry if env_registry is not None
                              else load_env_registry(env_registry_path, self._schema) if Category.ENV & self._categories
                              else {})
        self._overlaps = load_overlaps() if overlaps is None else overlaps
        self._overlaps_by_env = overlaps_by_env(self._overlaps)
        self._language = i18n.set_language(language)
        self._rows: dict[str, PropertyRow] = {}
        self._pages: list[_Page] = []
        self._passthrough: dict[str, Any] = {}
        self._file_path: Path | None = None
        self._refresh_pending = False
        self._json_dirty = False
        self._outer = QtWidgets.QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._body = self._build_ui()
        self._outer.addWidget(self._body)
        self._refresh_json()
        self._apply_filter()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> QtWidgets.QWidget:
        props: dict[str, JsonSchema] = self._schema.get("properties", {})
        required = set(self._schema.get("required", []))
        self._rows = {}
        self._pages = []

        # 툴바
        self._search = QtWidgets.QLineEdit()
        self._search.setPlaceholderText(tr("Search setting keys and descriptions…"))
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._apply_filter)
        self._only_set = QtWidgets.QCheckBox(tr("Set only"))
        self._only_set.toggled.connect(self._apply_filter)
        open_btn = QtWidgets.QPushButton(tr("Open…"))
        open_btn.clicked.connect(self._open_dialog)
        save_btn = QtWidgets.QPushButton(tr("Save…"))
        save_btn.clicked.connect(self._save_dialog)
        clear_btn = QtWidgets.QPushButton(tr("Clear all"))
        clear_btn.clicked.connect(self.clear)
        self._status = QtWidgets.QLabel()
        self._status.setStyleSheet(MUTED)
        self._status.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Preferred)
        self._status.setMinimumWidth(self._status.fontMetrics().horizontalAdvance(tr("000 keys set")) + 8)
        self._overlap_label = QtWidgets.QLabel()
        self._overlap_label.setStyleSheet("color: #d08a00; font-weight: bold;")
        self._overlap_label.hide()
        bar = QtWidgets.QHBoxLayout()
        bar.addWidget(self._search, 1)
        bar.addWidget(self._overlap_label)
        bar.addWidget(self._only_set)
        bar.addWidget(open_btn)
        bar.addWidget(save_btn)
        bar.addWidget(clear_btn)
        bar.addWidget(self._status)

        # 카테고리 페이지
        self._nav = QtWidgets.QListWidget()
        self._nav.setMaximumWidth(340)
        self._nav.setMinimumWidth(150)
        self._stack = QtWidgets.QStackedWidget()
        for cid, keys in categorize(list(props), self._categories):
            rows = []
            for key in keys:
                row = PropertyRow(key, resolve_ref(props[key], self._schema), self._schema, 0, key in required,
                                  related=self._overlaps.get(key))
                row.changed.connect(self._on_changed)
                row.envLinkActivated.connect(self.showEnvVariable)
                self._rows[key] = row
                rows.append(row)
            page = _Page(cid, tr(CATEGORY_TITLES[cid]), rows)
            self._pages.append(page)
            self._stack.addWidget(page)
            self._nav.addItem(page.title)

        # env 페이지
        self._env: EnvEditor | None = None
        self._env_index = -1
        if Category.ENV & self._categories:
            env_schema = resolve_ref(props.get(ENV_KEY, {"type": "object"}), self._schema)
            self._env = EnvEditor(env_schema, self._schema, self._env_registry, related=self._overlaps_by_env)
            self._env.changed.connect(self._on_changed)
            self._env_index = self._stack.addWidget(self._env)
            self._nav.addItem(tr(CATEGORY_TITLES[ENV_ID]))

        # JSON 페이지
        self._json: QtWidgets.QPlainTextEdit | None = None
        self._json_index = -1
        if Category.JSON & self._categories:
            self._build_json_page()
        self._json_dirty = False

        self._nav.currentRowChanged.connect(self._on_nav)
        self._nav.setCurrentRow(0)

        splitter = QtWidgets.QSplitter()
        splitter.addWidget(self._nav)
        splitter.addWidget(self._stack)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([250, 800])

        body = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(body)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addLayout(bar)
        lay.addWidget(splitter, 1)
        self._update_nav_counts()
        return body

    def _build_json_page(self) -> None:
        json_page = QtWidgets.QWidget()
        jv = QtWidgets.QVBoxLayout(json_page)
        jv.setContentsMargins(8, 8, 8, 8)
        self._json = QtWidgets.QPlainTextEdit()
        self._json.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont))
        self._json.setTabChangesFocus(True)
        self._json.textChanged.connect(self._on_json_text)
        self._json_error = QtWidgets.QLabel()
        self._json_error.setStyleSheet("color: #d33;")
        self._json_error.setWordWrap(True)
        apply_btn = QtWidgets.QPushButton(tr("Apply JSON"))
        apply_btn.setToolTip(tr("Parse the text and load it into the form"))
        apply_btn.clicked.connect(self._apply_json_text)
        copy_btn = QtWidgets.QPushButton(tr("Copy"))
        copy_btn.clicked.connect(lambda: QtWidgets.QApplication.clipboard().setText(self.GetSetting()))
        jb = QtWidgets.QHBoxLayout()
        jb.addWidget(apply_btn)
        jb.addWidget(copy_btn)
        jb.addStretch(1)
        jv.addWidget(self._json, 1)
        jv.addWidget(self._json_error)
        jv.addLayout(jb)
        self._json_index = self._stack.addWidget(json_page)
        self._nav.addItem(tr(CATEGORY_TITLES[JSON_ID]))

    # ------------------------------------------------------------------ 현지화
    def language(self) -> str:
        return self._language

    def setLanguage(self, language: str | None) -> str:
        """언어 전환: UI 를 다시 만들고 현재 값을 유지한다. 적용된 언어 코드를 돌려준다."""
        applied = i18n.set_language(language)
        if applied == self._language:
            return applied
        self._language = applied
        data = self.settings()
        current = self._nav.currentRow()
        old = self._body
        self._body = self._build_ui()
        self._outer.replaceWidget(old, self._body)
        old.hide()
        old.deleteLater()
        self.setSettings(data)
        self._nav.setCurrentRow(current)
        self.languageChanged.emit(applied)
        return applied

    @staticmethod
    def availableLanguages() -> list[str]:
        return i18n.available_languages()

    # ------------------------------------------------------------------ 공개 API
    def schema(self) -> JsonSchema:
        return self._schema

    def showManagedOnly(self) -> bool:
        return self._show_managed

    def setShowManagedOnly(self, show: bool) -> None:
        """관리형(managed/policy) 설정에서만 유효한 키의 표시 여부. 값은 보존되어 출력에는 그대로 남는다."""
        show = bool(show)
        if show == self._show_managed:
            return
        self._show_managed = show
        self._apply_filter()

    def managedOnlyKeys(self) -> list[str]:
        """관리형 전용으로 판별된 최상위 키(현재 노출 카테고리 기준)."""
        return [k for k, r in self._rows.items() if r.managed_only]

    def categories(self) -> Category:
        """생성 시 지정한 카테고리 비트 플래그."""
        return self._categories

    def overlapTable(self) -> dict[str, list[dict[str, str]]]:
        """설정 키 ↔ env 변수 겹침 표(문서에서 추출). {key: [{"env", "precedence", "note"}]}"""
        return self._overlaps

    def overlaps(self) -> list[dict[str, str]]:
        """설정 키와 짝 env 변수가 **둘 다** 설정된 항목. [{"setting", "env", "precedence"}]"""
        out: list[dict[str, str]] = []
        env = self._env.value() if self._env is not None else self._passthrough.get(ENV_KEY, {})
        if not isinstance(env, dict):
            env = {}
        for key, entries in self._overlaps.items():
            row = self._rows.get(key)
            key_set = row.included() if row is not None else key in self._passthrough
            if not key_set:
                continue
            for e in entries:
                if e["env"] in env:
                    out.append({"setting": key, "env": e["env"], "precedence": e.get("precedence", "related")})
        return out

    def showEnvVariable(self, name: str) -> bool:
        """env 페이지로 이동해 해당 변수만 필터링. env 페이지가 없으면 False."""
        if self._env is None:
            return False
        self.setCurrentCategory(ENV_ID)
        self._env.setFilterText(name)
        return True

    def envEditor(self) -> EnvEditor | None:
        """env 페이지 편집기. Category.ENV 가 제외되었으면 None."""
        return self._env

    def rowFor(self, key: str | SettingKey) -> PropertyRow | None:
        return self._rows.get(SettingKey.coerce(key))

    # ------------------------------------------------------------------ 단건 접근 (enum 키)
    def settingValue(self, key: str | SettingKey, default: Any = None) -> Any:
        """최상위 설정 키 하나의 값. 미설정이면 default. env 는 envValue()/UpdateEnv() 를 쓴다."""
        k = SettingKey.coerce(key)
        if k == ENV_KEY:
            env = self._env.value() if self._env is not None else self._passthrough.get(ENV_KEY)
            return env if env else default
        row = self._rows.get(k)
        if row is not None:
            return row.value() if row.included() else default
        return self._passthrough.get(k, default)

    def setSettingValue(self, key: str | SettingKey, value: Any) -> None:
        """최상위 설정 키 하나를 설정. value 가 None 이면 해제. 노출되지 않은 카테고리의 키는 보존 영역에 기록된다."""
        k = SettingKey.coerce(key)
        self._check_value(k, value)
        if k == ENV_KEY:
            self.UpdateEnv({}, replace=value if value is not None else {})
            return
        row = self._rows.get(k)
        if row is not None:
            if value is None:
                row.setIncluded(False)
                row.editor.reset()
            else:
                row.setValue(value)
        elif value is None:
            self._passthrough.pop(k, None)
        else:
            self._passthrough[k] = value
        self._on_changed()

    def unsetSetting(self, key: str | SettingKey) -> None:
        self.setSettingValue(key, None)

    def envValue(self, name: str | EnvVar, default: str | None = None) -> str | None:
        """env 변수 하나의 값. 미설정이면 default."""
        n = EnvVar.coerce(name)
        if self._env is not None:
            return self._env.variable(n) if self._env.isSet(n) else default
        env = self._passthrough.get(ENV_KEY)
        return env.get(n, default) if isinstance(env, dict) else default

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
        "env" 키가 있으면 UpdateEnv 와 같은 병합 규칙을 적용한다. 갱신 후 settings() 를 돌려준다.
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
        replace 를 주면 병합 대신 env 전체를 그 dict 로 바꾼다. 갱신 후 env dict 를 돌려준다.
        """
        obj = self._parse_object(data)
        if self._env is None:
            raise HiddenKeyError([str(ENV_KEY)])
        if replace is not None:
            if not isinstance(replace, dict):
                raise ValueError("env must be an object")
            obj = replace
            merged: dict[str, str] = {}
        else:
            merged = dict(self._env.value()) if self._env is not None else dict(self._passthrough.get(ENV_KEY) or {})
        for name, value in obj.items():
            n = EnvVar.coerce(name)
            if value is None:
                merged.pop(n, None)
            else:
                merged[n] = str(value)
        self._env.setValue(merged)
        self._on_changed()
        return dict(merged)

    def settings(self) -> dict[str, Any]:
        """현재 설정을 dict 로. 체크된(설정된) 키만 포함하며 키 순서는 스키마 순서."""
        out: dict[str, Any] = {}
        for key in self._schema.get("properties", {}):
            if key == ENV_KEY:
                if self._env is not None:
                    env = self._env.value()
                    if env:
                        out[ENV_KEY] = env
                continue
            row = self._rows.get(key)
            if row is not None and row.included():
                out[key] = row.value()
        for k, v in self._passthrough.items():
            out.setdefault(k, v)
        return out

    def setSettings(self, data: dict[str, Any] | None, *, trusted: bool = False) -> None:
        """설정 전체를 교체한다.

        trusted=False(기본): 이 위젯에 노출되지 않은 키(숨긴 카테고리·관리형 전용·env 페이지 없음 등)는
        현재 보존값과 동일할 때만 허용하고, 바뀌었으면 HiddenKeyError 를 낸다(우회 방지).
        trusted=True: 파일 등 신뢰 소스에서 읽은 문서. 노출되지 않은 키는 읽기 전용으로 보존한다.
        """
        data = dict(data or {})
        if not trusted:
            self._check_document(data)
        self._passthrough = {}
        for key, row in self._rows.items():
            if key in data:
                row.setValue(data[key])
            else:
                row.setIncluded(False)
                row.editor.reset()
        if self._env is not None:
            self._env.setValue(data.get(ENV_KEY, {}))
        for k, v in data.items():
            if k not in self._rows and (k != ENV_KEY or self._env is None):
                self._passthrough[k] = v  # 제외된 카테고리·미지 키는 보존만 한다
        self._on_changed()

    # ------------------------------------------------------------------ 노출 정책(우회 방지)
    def isKeyExposed(self, key: str | SettingKey) -> bool:
        """이 위젯에서 편집 가능한(노출된) 최상위 키인지."""
        k = SettingKey.coerce(key)
        if k == ENV_KEY:
            return self._env is not None
        row = self._rows.get(k)
        if row is not None:
            return self._show_managed or not row.managed_only
        if k in self._schema.get("properties", {}):
            return False  # 숨긴 카테고리
        return bool(Category.OTHER & self._categories)  # 스키마 밖 키는 OTHER 가 노출될 때만

    def _hidden_current(self, k: str) -> Any:
        """노출되지 않은 키의 현재(보존) 값. 없으면 _MISSING."""
        row = self._rows.get(k)
        if row is not None:
            return row.value() if row.included() else _MISSING
        return self._passthrough.get(k, _MISSING)

    def _check_value(self, k: str, value: Any) -> None:
        """단건 변경 허용 검사: 키 노출 여부 + (관리형 숨김 시) 중첩 관리형 경로."""
        if not self.isKeyExposed(k):
            raise HiddenKeyError([k])
        if not self._show_managed and k != ENV_KEY and value is not None:
            prop = self._schema.get("properties", {}).get(k)
            if prop is not None:
                paths = find_managed_only_paths(prop, value, self._schema, k)
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
            elif self._hidden_current(k) != v:
                bad.append(k)
        for k in self._all_hidden_current_keys():
            if k not in data:
                bad.append(k)  # 숨긴 키 제거도 변경이다
        if bad:
            raise HiddenKeyError(sorted(set(bad)))

    def _all_hidden_current_keys(self) -> list[str]:
        keys = [k for k, r in self._rows.items() if r.included() and not self.isKeyExposed(k)]
        keys += [k for k in self._passthrough if not self.isKeyExposed(k)]
        return keys

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
        keep = {k: self._hidden_current(k) for k in self._all_hidden_current_keys()}
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

    def categoryIds(self) -> list[str]:
        ids = [p.category_id for p in self._pages]
        if self._env is not None:
            ids.append(ENV_ID)
        if self._json is not None:
            ids.append(JSON_ID)
        return ids

    def categoryTitles(self) -> list[str]:
        return [self._pages[i].title if i < len(self._pages) else tr(CATEGORY_TITLES[cid])
                for i, cid in enumerate(self.categoryIds())]

    def setCurrentCategory(self, id_or_title: str) -> bool:
        """카테고리 id('hooks', 'env', 'json') 또는 표시 제목으로 페이지 전환."""
        for names in (self.categoryIds(), self.categoryTitles()):
            if id_or_title in names:
                self._nav.setCurrentRow(names.index(id_or_title))
                return True
        return False

    # ------------------------------------------------------------------ 내부
    def _on_changed(self) -> None:
        if not self._refresh_pending:
            self._refresh_pending = True
            QtCore.QTimer.singleShot(0, self._flush_change)

    def _flush_change(self) -> None:
        self._refresh_pending = False
        self._refresh_json()
        self._update_nav_counts()
        self._update_overlap_warning()
        if self._only_set.isChecked():
            self._apply_filter()
        elif not self._show_managed:
            self._apply_nested_managed_filter()  # 로드로 새로 생긴 중첩 행 반영
        self.settingChanged.emit()

    def _update_overlap_warning(self) -> None:
        from .editors.containers import precedence_label

        pairs = self.overlaps()
        if not pairs:
            self._overlap_label.hide()
            return
        self._overlap_label.setText(tr("⚠ {n} overlapping", n=len(pairs)))
        self._overlap_label.setToolTip(tr("Both the setting and its environment variable are set:") + "\n" + "\n".join(
            f"{p['setting']} ↔ {p['env']} ({precedence_label(p['precedence'])})" for p in pairs))
        self._overlap_label.show()

    def _refresh_json(self) -> None:
        data = self.settings()
        if self._json is not None:
            text = json.dumps(data, indent=2, ensure_ascii=False)
            if self._json.toPlainText() != text:
                self._json.blockSignals(True)
                self._json.setPlainText(text)
                self._json.blockSignals(False)
            self._json_dirty = False
            self._json_error.clear()
        self._status.setText(tr("{n} keys set", n=len(data)))

    def _on_json_text(self) -> None:
        self._json_dirty = True

    def _apply_json_text(self) -> None:
        if self._json is None:
            return
        try:
            self.SetSetting(self._json.toPlainText())
            self._json_error.clear()
        except HiddenKeyError as e:
            self._json_error.setText(str(e))
        except ValueError as e:
            self._json_error.setText(tr("JSON error: {error}", error=e))

    def _on_nav(self, row: int) -> None:
        self._stack.setCurrentIndex(row)
        if row == self._json_index and not self._json_dirty:
            self._refresh_json()

    def _apply_filter(self, *_: Any) -> None:
        text = self._search.text().strip().lower()
        only = self._only_set.isChecked()
        for page in self._pages:
            page.applyFilter(text, only, self._show_managed)
        self._apply_nested_managed_filter()
        if self._env is not None:
            self._env.setFilterText(self._search.text())
        self._update_nav_counts()

    def _apply_nested_managed_filter(self) -> None:
        """중첩 객체 안의 관리형 전용 행(sandbox.enabledPlatforms 등)도 숨김/표시."""
        top = set(self._rows.values())
        for row in self._body.findChildren(PropertyRow):
            if row in top or not row.managed_only:
                continue
            row.setVisible(self._show_managed)

    def _update_nav_counts(self) -> None:
        text = self._search.text().strip().lower()
        only = self._only_set.isChecked()
        for i, page in enumerate(self._pages):
            rows = [r for r in page.rows if self._show_managed or not r.managed_only]
            n_set = sum(1 for r in rows if r.included())
            if text or only:
                n_match = sum(1 for r in rows if (not text or r.matches(text)) and (not only or r.included()))
                label = f"{page.title}  ({n_match})"
            else:
                label = f"{page.title}  ({n_set}/{len(rows)})" if n_set else page.title
            self._nav.item(i).setText(label)
        if self._env is not None:
            env_title = tr(CATEGORY_TITLES[ENV_ID])
            env_n = len(self._env.value())
            self._nav.item(self._env_index).setText(f"{env_title}  ({env_n})" if env_n else env_title)

    def _open_dialog(self) -> None:
        start = str(self._file_path or Path.home() / ".claude")
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, tr("Open settings.json"), start, tr("JSON (*.json);;All files (*)"))
        if path:
            try:
                self.loadFile(path)
            except (OSError, ValueError) as e:
                QtWidgets.QMessageBox.warning(self, tr("Open failed"), str(e))

    def _save_dialog(self) -> None:
        start = str(self._file_path or Path.home() / ".claude" / "settings.json")
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, tr("Save settings.json"), start, tr("JSON (*.json)"))
        if path:
            try:
                self.saveFile(path)
            except OSError as e:
                QtWidgets.QMessageBox.warning(self, tr("Save failed"), str(e))
