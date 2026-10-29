"""QClaudeCodeSettingEditorWidget: Claude Code settings.json 전체를 편집하는 PySide6 위젯.

페이지(카테고리)와 env 편집기는 **지연 구축**된다: 생성 시에는 내비게이션과 키 메타데이터만 만들고,
좌측에서 처음 선택되거나 rowFor()/envEditor() 로 필요해질 때 행을 만든다. 그 전까지 값은
_pending 에 보관되며 settings()/setSettings() 의 의미는 구축 여부와 무관하게 같다.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from . import i18n
from ._version import __version__ as CLAUDE_CODE_VERSION
from .categories import CATEGORY_TITLES, Category, categorize
from .constants import ENV_ID, ENV_KEY, JSON_ID, MUTED, Precedence, Scope
from .editors import PropertyRow
from .env_editor import EnvEditor
from .i18n import tr
from .keys import SettingKey, setting_info
from .pages import KeyMeta, _Page
from .schema import EnvVarInfo, JsonSchema, load_env_registry, load_overlaps, load_schema, overlaps_by_env, resolve_ref
from .spec import Version
from .widget_api import _MISSING, HiddenKeyError, SettingsApiMixin

__all__ = ["QClaudeCodeSettingEditorWidget", "HiddenKeyError"]


class QClaudeCodeSettingEditorWidget(SettingsApiMixin, QtWidgets.QWidget):
    """Claude Code settings.json 편집 위젯.

    공개 API (widget_api.SettingsApiMixin 참조)
    - settings() / setSettings(dict)      : 파이썬 dict 로 읽기/쓰기
    - GetSetting(indent=2) -> str         : 설정을 JSON 문자열로
    - GetSettingJsonl() -> str            : 설정을 한 줄 JSON(JSONL 한 레코드)로
    - SetSetting(text: str)               : JSON 문자열로부터 로드
    - loadFile(path) / saveFile(path)     : 파일 입출력
    - clear()                             : 노출된 키 모두 해제
    - setLanguage(code) / language()      : 현지화 (locales/qccse_<code>.ts 또는 .qm 이 있으면 사용 가능)
    - settingChanged (Signal)             : 값이 바뀔 때마다 (같은 이벤트 루프 턴의 변경은 한 번)
    """

    settingChanged = QtCore.Signal()
    fileLoaded = QtCore.Signal(str)
    fileSaved = QtCore.Signal(str)
    languageChanged = QtCore.Signal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None, *, schema: JsonSchema | None = None,
                 schema_path: str | Path | None = None, env_registry_path: str | Path | None = None,
                 env_registry: dict[str, EnvVarInfo] | None = None, language: str | None = None,
                 categories: Category = Category.ALL, overlaps: dict[str, list[dict[str, str]]] | None = None,
                 targetScope: Scope = Scope.USER, targetVersion: str | None = None):
        """categories: 좌측에 노출할 카테고리 비트 플래그. 제외된 카테고리의 키는 편집할 수 없고,
        로드된 값은 _passthrough 로 보존되어 그대로 다시 내보낸다.
        targetScope: 편집 대상 설정 파일(Scope 비트 플래그, 기본 USER = ~/.claude/settings.json).
        그 파일들 중 어디에서도 효력이 없는 키(예: USER 대상일 때 Managed 전용 키)는 숨긴다. ANY_FILE 이면 전부.
        targetVersion: 대상 Claude Code 버전("2.1.250"). 그 버전에 없는 키(이후 추가·이전 제거)는 숨긴다.
        None 이면 버전으로 거르지 않는다. 숨겨도 로드된 값은 보존되어 출력에 그대로 남는다."""
        super().__init__(parent)
        self._categories = Category(categories)
        self._target_scope = self._valid_scope(targetScope)
        self._target_version = self._valid_version(targetVersion)
        self._env_enabled = bool(Category.ENV & self._categories)
        self._schema: JsonSchema = schema if schema is not None else load_schema(schema_path)
        self._env_registry_path = env_registry_path
        self._env_registry: dict[str, EnvVarInfo] | None = env_registry  # env 페이지 구축 시 로드
        self._overlaps = load_overlaps() if overlaps is None else overlaps
        self._overlaps_by_env = overlaps_by_env(self._overlaps)
        self._language = i18n.set_language(language)
        self._rows: dict[str, PropertyRow] = {}          # 구축된 행
        self._pending: dict[str, Any] = {}               # 미구축 페이지 키(및 미구축 env: "env")의 값
        self._passthrough: dict[str, Any] = {}           # 노출되지 않은 키의 보존값
        self._meta: dict[str, KeyMeta] = {}
        self._page_by_key: dict[str, _Page] = {}
        self._pages: list[_Page] = []
        self._env: EnvEditor | None = None
        self._file_path: Path | None = None
        self._json_dirty = False
        # 0ms 디바운스 타이머. self 를 부모로 두어 위젯(C++)이 파괴되면 함께 죽는다 —
        # QTimer.singleShot(0, bound_method) 은 위젯 파괴 뒤에도 발화해 stale 행에 접근했다.
        self._flush_timer = QtCore.QTimer(self)
        self._flush_timer.setSingleShot(True)
        self._flush_timer.setInterval(0)
        self._flush_timer.timeout.connect(self._flush_change)
        self._outer = QtWidgets.QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._body = self._build_ui()
        self._outer.addWidget(self._body)
        self._refresh_json()
        self._apply_filter()

    # ------------------------------------------------------------------ UI 구축
    def _build_ui(self) -> QtWidgets.QWidget:
        props: dict[str, JsonSchema] = self._schema.get("properties", {})
        required = set(self._schema.get("required", []))
        self._rows = {}
        self._pending = {}
        self._pages = []
        self._page_by_key = {}
        self._meta = {}
        self._env = None
        self._env_placeholder: QtWidgets.QWidget | None = None

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

        # 카테고리 페이지(지연 구축): 키 메타만 만들고 행은 만들지 않는다
        self._nav = QtWidgets.QListWidget()
        self._nav.setMaximumWidth(340)
        self._nav.setMinimumWidth(150)
        self._stack = QtWidgets.QStackedWidget()
        for cid, keys in categorize(list(props), self._categories):
            for key in keys:
                self._meta[key] = KeyMeta.build(key, resolve_ref(props[key], self._schema), key in required,
                                                self._overlaps.get(key))
            page = _Page(cid, tr(CATEGORY_TITLES[cid]), keys, self._meta, self._make_row, self._is_set)
            for key in keys:
                self._page_by_key[key] = page
            self._pages.append(page)
            self._stack.addWidget(page)
            self._nav.addItem(page.title)

        # env 페이지(지연 구축): 자리표시자만 넣는다
        self._env_index = -1
        if self._env_enabled:
            self._env_placeholder = QtWidgets.QWidget()
            self._env_index = self._stack.addWidget(self._env_placeholder)
            self._nav.addItem(tr(CATEGORY_TITLES[ENV_ID]))

        # JSON 페이지
        self._json: QtWidgets.QPlainTextEdit | None = None
        self._json_index = -1
        if Category.JSON & self._categories:
            self._build_json_page()
        self._json_dirty = False

        self._nav.currentRowChanged.connect(self._on_nav)
        self._nav.setCurrentRow(0)  # 첫 페이지만 구축된다

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

    # ------------------------------------------------------------------ 지연 구축
    def _make_row(self, key: str) -> PropertyRow:
        """페이지가 구축될 때 호출: 행을 만들고 pending 값을 옮겨 담는다."""
        meta = self._meta[key]
        row = PropertyRow(key, meta.schema, self._schema, 0, meta.required, related=meta.related)
        row.changed.connect(self._on_changed)
        row.envLinkActivated.connect(self.showEnvVariable)
        self._rows[key] = row
        if key in self._pending:
            row.setValue(self._pending.pop(key))
        return row

    def _ensure_page(self, page: _Page) -> None:
        if page.built:
            return
        page.build()
        page.applyFilter(self._search.text().strip().lower(), self._only_set.isChecked(), self._applicable)
        self._apply_nested_filter(page)

    def _ensure_env(self) -> EnvEditor | None:
        """env 편집기를 처음 필요할 때 만든다. Category.ENV 가 없으면 None."""
        if not self._env_enabled:
            return None
        if self._env is None:
            if self._env_registry is None:
                self._env_registry = load_env_registry(self._env_registry_path, self._schema)
            env_schema = resolve_ref(self._schema.get("properties", {}).get(ENV_KEY, {"type": "object"}), self._schema)
            env = EnvEditor(env_schema, self._schema, self._env_registry, related=self._overlaps_by_env)
            env.setValue(self._pending.pop(ENV_KEY, {}))
            env.changed.connect(self._on_changed)
            env.setFilterText(self._search.text())
            if self._env_placeholder is not None:
                self._stack.removeWidget(self._env_placeholder)
                self._env_placeholder.deleteLater()
                self._env_placeholder = None
            self._stack.insertWidget(self._env_index, env)
            self._env = env
        return self._env

    def ensureAllPagesBuilt(self) -> None:
        """모든 페이지와 env 편집기를 즉시 구축한다(테스트·일괄 검사용)."""
        for page in self._pages:
            self._ensure_page(page)
        self._ensure_env()

    # ------------------------------------------------------------------ 값 보관처 (SettingsApiMixin 이 사용)
    def _key_value(self, k: str) -> Any:
        """키의 현재 값(행 → pending → passthrough). 없으면 _MISSING."""
        row = self._rows.get(k)
        if row is not None:
            return row.value() if row.included() else _MISSING
        if k in self._pending:
            return self._pending[k]
        return self._passthrough.get(k, _MISSING)

    def _set_key_value(self, k: str, value: Any) -> None:
        """정책 검사 없이 값을 기록. value 가 None 이면 해제."""
        row = self._rows.get(k)
        if row is not None:
            if value is None:
                row.setIncluded(False)
                row.editor.reset()
            else:
                row.setValue(value)
            return
        store = self._pending if k in self._page_by_key else self._passthrough
        if value is None:
            store.pop(k, None)
        else:
            store[k] = value

    def _is_set(self, k: str) -> bool:
        return self._key_value(k) is not _MISSING

    def _set_keys(self) -> list[str]:
        keys = [k for k, r in self._rows.items() if r.included()]
        keys += [k for k in self._pending if k != ENV_KEY]
        keys += [k for k in self._passthrough if k != ENV_KEY]
        return keys

    def _env_dict(self) -> dict[str, str]:
        if self._env is not None:
            return self._env.value()
        store = self._pending if self._env_enabled else self._passthrough
        env = store.get(ENV_KEY)
        return dict(env) if isinstance(env, dict) else {}

    def _set_env_dict(self, env: dict[str, Any]) -> None:
        if self._env is not None:
            self._env.setValue(env)
            return
        store = self._pending if self._env_enabled else self._passthrough
        if env:
            store[ENV_KEY] = dict(env)
        else:
            store.pop(ENV_KEY, None)

    def _replace_all(self, data: dict[str, Any]) -> None:
        """setSettings 의 실제 교체: 행/pending/passthrough/env 를 모두 새 문서로 바꾼다."""
        self._passthrough = {}
        self._pending = {}
        for key, row in self._rows.items():
            if key in data:
                row.setValue(data[key])
            else:
                row.setIncluded(False)
                row.editor.reset()
        for k, v in data.items():
            if k == ENV_KEY:
                self._set_env_dict(v if isinstance(v, dict) else {})
            elif k not in self._rows:
                (self._pending if k in self._page_by_key else self._passthrough)[k] = v
        if ENV_KEY not in data:
            self._set_env_dict({})

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
        self.setSettings(data, trusted=True)
        self._nav.setCurrentRow(current)
        self.languageChanged.emit(applied)
        return applied

    @staticmethod
    def availableLanguages() -> list[str]:
        return i18n.available_languages()

    # ------------------------------------------------------------------ 공개 API (UI 쪽)
    def schema(self) -> JsonSchema:
        return self._schema

    def targetScope(self) -> Scope:
        return self._target_scope

    def setTargetScope(self, scope: Scope) -> None:
        """편집 대상 설정 파일(Scope 플래그). 그 파일들에서 효력이 없는 키는 숨기고 API 로도 바꿀 수 없다."""
        scope = self._valid_scope(scope)
        if scope != self._target_scope:
            self._target_scope = scope
            self._apply_filter()

    def targetVersion(self) -> str | None:
        """대상 Claude Code 버전("2.1.250"). None 이면 버전 필터 없음."""
        return str(self._target_version) if self._target_version is not None else None

    def setTargetVersion(self, version: str | None) -> None:
        """대상 Claude Code 버전. 그 버전에 없는 키(이후 추가·이전 제거)는 숨긴다. None 이면 필터 해제."""
        v = self._valid_version(version)
        if v != self._target_version:
            self._target_version = v
            self._apply_filter()

    @staticmethod
    def latestVersion() -> str:
        """번들 메타데이터의 기준 Claude Code 버전(= 패키지 버전)."""
        return CLAUDE_CODE_VERSION

    @staticmethod
    def _valid_scope(scope: Scope) -> Scope:
        scope = Scope(scope)
        if not scope or scope & ~Scope.ANY_FILE:
            raise ValueError(tr("targetScope must be a non-empty combination of USER, PROJECT, LOCAL and MANAGED"))
        return scope

    @staticmethod
    def _valid_version(version: str | None) -> Version | None:
        return None if version is None or not str(version).strip() else Version.parse(str(version))

    def isKeyApplicable(self, path: str | SettingKey) -> bool:
        """키(또는 중첩 경로 "sandbox.bwrapPath")가 대상 스코프·버전에서 효력이 있는지. 메타데이터가 없으면 True."""
        info = setting_info(SettingKey.coerce(path))
        return info is None or info.applicable(self._target_scope, self._target_version)

    _applicable = isKeyApplicable

    def categories(self) -> Category:
        """생성 시 지정한 카테고리 비트 플래그."""
        return self._categories

    def overlapTable(self) -> dict[str, list[dict[str, str]]]:
        """설정 키 ↔ env 변수 겹침 표(문서에서 추출). {key: [{"env", "precedence", "note"}]}"""
        return self._overlaps

    def overlaps(self) -> list[dict[str, str]]:
        """설정 키와 짝 env 변수가 **둘 다** 설정된 항목. [{"setting", "env", "precedence"}]"""
        env = self._env_dict()
        out: list[dict[str, str]] = []
        for key, entries in self._overlaps.items():
            if not self._is_set(key):
                continue
            for e in entries:
                if e["env"] in env:
                    out.append({"setting": key, "env": e["env"], "precedence": e.get("precedence", Precedence.RELATED)})
        return out

    def showEnvVariable(self, name: str) -> bool:
        """env 페이지로 이동해 해당 변수만 필터링. env 페이지가 없으면 False."""
        if not self._env_enabled:
            return False
        self.setCurrentCategory(ENV_ID)
        env = self._ensure_env()
        if env is not None:
            env.setFilterText(name)
        return True

    def envEditor(self) -> EnvEditor | None:
        """env 페이지 편집기(필요 시 구축). Category.ENV 가 제외되었으면 None."""
        return self._ensure_env()

    def rowFor(self, key: str | SettingKey) -> PropertyRow | None:
        """최상위 키의 행(그 페이지를 필요 시 구축). 노출되지 않은 카테고리의 키면 None."""
        k = SettingKey.coerce(key)
        page = self._page_by_key.get(k)
        if page is None:
            return None
        self._ensure_page(page)
        return self._rows.get(k)

    def categoryIds(self) -> list[str]:
        ids = [p.category_id for p in self._pages]
        if self._env_enabled:
            ids.append(ENV_ID)
        if self._json is not None:
            ids.append(JSON_ID)
        return ids

    def categoryTitles(self) -> list[str]:
        return [self._pages[i].title if i < len(self._pages) else tr(CATEGORY_TITLES[cid])
                for i, cid in enumerate(self.categoryIds())]

    def setCurrentCategory(self, id_or_title: str) -> bool:
        """카테고리 id('hooks', 'env', 'json') 또는 표시 제목으로 페이지 전환(필요 시 구축)."""
        for names in (self.categoryIds(), self.categoryTitles()):
            if id_or_title in names:
                self._nav.setCurrentRow(names.index(id_or_title))
                return True
        return False

    # ------------------------------------------------------------------ 내부: 변경 반영
    def _on_changed(self) -> None:
        """변경을 0ms 뒤 한 번으로 합쳐 반영한다(같은 이벤트 루프 턴의 변경은 한 번만 갱신)."""
        if not self._flush_timer.isActive():
            self._flush_timer.start()

    def _flush_change(self) -> None:
        self._flush_timer.stop()
        self._refresh_json()
        self._update_nav_counts()
        self._update_overlap_warning()
        if self._only_set.isChecked():
            self._apply_filter()
        else:
            self._apply_nested_filter()  # 로드로 새로 생긴 중첩 행 반영
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
        if 0 <= row < len(self._pages):
            self._ensure_page(self._pages[row])
        elif row == self._env_index:
            self._ensure_env()
        self._stack.setCurrentIndex(row)
        if row == self._json_index and not self._json_dirty:
            self._refresh_json()

    # ------------------------------------------------------------------ 내부: 필터·카운트
    def _apply_filter(self, *_: Any) -> None:
        text = self._search.text().strip().lower()
        only = self._only_set.isChecked()
        for page in self._pages:
            page.applyFilter(text, only, self._applicable)
        self._apply_nested_filter()
        if self._env is not None:
            self._env.setFilterText(self._search.text())
        self._update_nav_counts()

    def _apply_nested_filter(self, root: QtWidgets.QWidget | None = None) -> None:
        """중첩 객체 안의 행(sandbox.bwrapPath 등)도 대상 스코프·버전에 맞춰 숨김/표시."""
        top = set(self._rows.values())
        for row in (root or self._body).findChildren(PropertyRow):
            if row in top or row.info is None:
                continue
            row.setVisible(row.info.applicable(self._target_scope, self._target_version))

    def _update_nav_counts(self) -> None:
        text = self._search.text().strip().lower()
        only = self._only_set.isChecked()
        for i, page in enumerate(self._pages):
            n_match, n_set, n_total = page.count(text, only, self._applicable)
            if text or only:
                label = f"{page.title}  ({n_match})"
            else:
                label = f"{page.title}  ({n_set}/{n_total})" if n_set else page.title
            self._nav.item(i).setText(label)
        if self._env_enabled:
            env_title = tr(CATEGORY_TITLES[ENV_ID])
            env_n = len(self._env_dict())
            self._nav.item(self._env_index).setText(f"{env_title}  ({env_n})" if env_n else env_title)

    # ------------------------------------------------------------------ 파일 대화상자
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
