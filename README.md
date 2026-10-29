# QClaudeCodeSettingEditorWidget

Claude Code `settings.json` 의 **모든 키**를 GUI로 편집하는 PySide6 위젯.
키 목록·스코프·버전은 공식 문서 [All settings (settings-reference)](https://code.claude.com/docs/en/settings-reference)가 기준이고,
키별 JSON 구조는 [schemastore 의 claude-code-settings.json](https://www.schemastore.org/claude-code-settings.json) 으로 보충한다
(schemastore 에 아직 없는 문서 키는 문서의 Type 설명에서 스키마를 만들어 주입). 그 병합 스키마로부터 편집기를 자동 생성한다.
`env` 는 스키마의 변수 목록에 [환경 변수 문서](https://code.claude.com/docs/en/env-vars)를 병합한 전용 표로 편집한다.

**패키지 버전 = 번들 메타데이터를 생성한 Claude Code 버전**(현재 `2.1.312`, `qclaudecodesettingeditorwidget/_version.py`).

## 설치·실행

```bash
pip install -e .            # PySide6 포함
pip install -e .[dev]       # + pytest / pytest-qt / jsonschema
python -m qclaudecodesettingeditorwidget [~/.claude/settings.json]   # 테스트 메인윈도우 (확인 → 설정된 키만 JSON 표시)
python -m pytest            # 테스트 (오프스크린)
```

## 사용

```python
from PySide6 import QtWidgets
from qclaudecodesettingeditorwidget import QClaudeCodeSettingEditorWidget

app = QtWidgets.QApplication([])
w = QClaudeCodeSettingEditorWidget(language="ko")   # 생략 시 QCCSE_LANG → 시스템 로케일 → en
w.SetSetting('{"model": "opus", "env": {"API_TIMEOUT_MS": "1200000"}}')   # JSON 문자열 로드
w.show(); app.exec()

w.GetSetting()        # 들여쓰기된 JSON 문자열
w.GetSettingJsonl()   # 개행 없는 한 줄 JSON (JSONL 레코드)
w.settings()          # dict
```

| API | 설명 |
| --- | --- |
| `settings()` / `setSettings(dict)` | dict 로 읽기/쓰기. 체크된(설정된) 키만 포함, 순서는 스키마 순서 |
| `GetSetting(indent=2)` / `GetSettingJsonl()` | JSON 문자열 / 한 줄 JSON |
| `SetSetting(text)` | JSON 문자열 로드. 파싱 실패 시 `ValueError` |
| `loadFile(path)` / `saveFile(path=None)` | 파일 입출력 (`fileLoaded` / `fileSaved` 시그널) |
| `clear()` | 모든 키 해제 |
| `settingValue(key)` / `setSettingValue(key, v)` / `unsetSetting(key)` | 최상위 키 단건 (`SettingKey` 또는 문자열) |
| `envValue(name)` / `setEnvValue(name, v_or_None)` | env 변수 단건 (`EnvVar` 또는 문자열) |
| `UpdateSetting(json_or_dict)` / `UpdateEnv(json_or_dict, replace=None)` | JSON 병합 갱신 (`null` → 해제) |
| `envEditor().setVariable(name, value_or_None)` | env 변수 설정/해제 (env 페이지 편집기 직접) |
| `rowFor(key)` | 최상위 키의 `PropertyRow` (`included()`, `setValue()`, `editor`) |
| `setCurrentCategory(id_or_title)` / `categoryIds()` / `categoryTitles()` | 페이지 전환 (`"hooks"`, `"env"`, `"json"` …) |
| `setLanguage(code)` / `language()` / `availableLanguages()` | 현지화 전환 (`languageChanged` 시그널) |
| `categories()` | 생성 시 지정한 `Category` 플래그 |
| `targetScope()` / `setTargetScope(Scope)` | 편집 대상 설정 파일 (생성자 `targetScope=Scope.USER`) — 그 파일에서 효력 없는 키 숨김 |
| `targetVersion()` / `setTargetVersion(str \| None)` / `latestVersion()` | 대상 Claude Code 버전 (생성자 `targetVersion=None` = 필터 없음) |
| `isKeyApplicable(key_or_path)` / `inapplicableKeys()` | 대상 스코프·버전에서 효력이 있는지 / 그래서 숨긴 최상위 키 |
| `settingChanged` (Signal) | 값이 바뀔 때마다 (같은 이벤트 루프 턴 내 변경은 한 번으로 합침) |

## 키 enum·메타데이터와 단건·JSON 갱신

키 문자열 대신 enum 을 쓴다. `SettingKey`(최상위 설정 키 184개, `keys.py`)와 `EnvVar`(환경변수 441개, `env_keys.py`)는
`str` 겸용이라 **멤버 이름이 곧 키**다: `SettingKey.model == "model"`, `EnvVar.API_TIMEOUT_MS == "API_TIMEOUT_MS"`.
식별자가 될 수 없는 `$schema` 만 `SettingKey.schema`(값 `"$schema"`)다. 위젯 내부(카테고리 표 등)도 이 enum 을 쓴다.

`SettingKey` 의 각 멤버는 값으로 **`SettingInfo` dataclass** 를 갖고, `.info` 로 꺼낸다(키 문자열 동작은 그대로).
중첩 경로(`sandbox.bwrapPath` 등 63개)는 `NESTED_SETTINGS`, 통합 조회는 `setting_info(path)`.
메타데이터는 문자열 대신 `constants.py` 의 enum(`Scope`·`JsonType`·`Topic`)과 `Version` 으로 적힌다 — 문자열은 키와 JSON 값(기본값·값 후보)뿐.

| `SettingInfo` 필드 | 내용 |
| --- | --- |
| `scope` | 효력이 있는 파일 — `Scope` 비트 플래그 (`USER`·`PROJECT`·`LOCAL`·`MANAGED`, `ANY_FILE`, `GLOBAL_CONFIG`=`~/.claude.json`) |
| `type` / `default` / `values` | `JsonType` 비트 플래그(`STRING \| NULL` 등) / 문서·스키마의 기본값 / 값 후보(배열이면 원소 후보) |
| `since` / `removed` | 도입·제거 `Version` (`None` = 미상 → 버전 필터에서 항상 있는 것으로 취급) |
| `deprecated` / `deprecated_since` / `replaced_by` | 사용 중단 여부·`Version`·대체 키의 `SettingInfo` |
| `topic` / `in_docs` / `in_schemastore` | 문서 주제 `Topic` / 출처 |
| 메서드 | `allowed_in(scope)`, `available_in(version)`, `applicable(scope, version)`, `deprecated_in(version)` |

```python
from qclaudecodesettingeditorwidget import EnvVar, Scope, SettingKey, Version, setting_info

SettingKey.availableModelsMatch.info   # SettingInfo("availableModelsMatch", scope=Scope.MANAGED, type=JsonType.STRING,
                                       #             default="prefix", values=("prefix", "exact"), since=Version(2, 1, 283),
                                       #             topic=Topic.MODEL, ...)
SettingKey.voiceEnabled.info.replaced_by.key    # "voice"
SettingKey.availableModelsMatch.info.available_in("2.1.250")   # False (Version 또는 "2.1.250" 문자열)
setting_info("sandbox.bwrapPath").scope         # Scope.MANAGED
```

`keys.py`·`env_keys.py` 는 `tools/refresh_resources.py` 가 생성하며(직접 수정 금지, 보정은 `tools/resource_overrides.json`),
테스트가 스키마·env 레지스트리와의 동기화를 검사한다.

```python
from qclaudecodesettingeditorwidget import EnvVar, SettingKey

w.setSettingValue(SettingKey.model, "opus");  w.settingValue(SettingKey.model);  w.unsetSetting(SettingKey.model)
w.setEnvValue(EnvVar.API_TIMEOUT_MS, "1200000");  w.envValue(EnvVar.API_TIMEOUT_MS)

w.UpdateSetting('{"effortLevel": "high", "fastMode": null}')   # 설정 병합: null 이면 해제, 결과 settings() 반환
w.UpdateEnv('{"API_TIMEOUT_MS": "1200000", "DEBUG": null}')     # env 병합: null 이면 해제, 결과 env dict 반환
w.UpdateEnv("{}", replace={"ONLY": "this"})                     # env 전체 교체
```

`UpdateSetting` / `UpdateEnv` 는 JSON 문자열과 dict 를 모두 받고, 키는 문자열·enum 멤버·멤버 이름(`"schema"`) 어느 것이든 된다.
노출되지 않은 키(숨긴 카테고리·대상 스코프/버전 밖·env 페이지 없음)는 읽기(`settingValue`/`envValue`)만 되고 갱신하면 `HiddenKeyError` 다(아래 우회 방지 정책).

## 카테고리 선택 (비트 플래그)

별도 앱에서 일부 설정만 열어 주고 싶을 때 생성자의 `categories` 에 `Category` 플래그를 넘긴다.

```python
from qclaudecodesettingeditorwidget import Category, QClaudeCodeSettingEditorWidget

w = QClaudeCodeSettingEditorWidget(categories=Category.MODEL | Category.HOOKS | Category.ENV)
w = QClaudeCodeSettingEditorWidget(categories=Category.ALL & ~Category.ADMIN)   # 관리형 설정만 제외
w = QClaudeCodeSettingEditorWidget(categories=Category.SETTINGS)                 # env·JSON 페이지 없이
```

| 플래그 | 페이지 |
| --- | --- |
| `AUTH` `MODEL` `PERMISSIONS` `HOOKS` `MCP` `PLUGINS` `SANDBOX` `CONTEXT` `GIT` `UI` `NOTIFICATIONS` `AGENTS` `IDE` `ADMIN` | 설정 카테고리 (`categories.py` 의 키 분류와 1:1) |
| `OTHER` | 스키마·문서 갱신으로 새로 생겨 분류되지 않은 키 |
| `ENV` / `JSON` | 환경 변수 페이지 / JSON 페이지 |
| `SETTINGS` | 위 설정 카테고리 전부 (`ENV`·`JSON` 제외) |
| `ALL` / `NONE` | 전부 / 없음 |

- 제외된 카테고리는 페이지가 아예 만들어지지 않으며 `rowFor(key)` 는 `None`, `Category.ENV` 가 없으면 `envEditor()` 도 `None`.
- 제외된 카테고리에 속한 키가 **파일에서 로드**되면 편집 불가 상태로 보존되어 `settings()`/`GetSetting()` 에 그대로 다시 나온다(값 유실 방지).
  숨긴 키까지 출력에서 빼려면 호출 측에서 걸러낸다. JSON 페이지가 켜져 있으면 그 JSON 에는 보존된 키가 보인다.

### 우회 방지 정책

생성자에서 정한 노출 범위(카테고리·`targetScope`·`targetVersion`·env 페이지)는 함수 API 로도 넘을 수 없다. `isKeyExposed(key)` 가 False 인 키는:

- `setSettingValue` / `unsetSetting` / `UpdateSetting` / `setEnvValue` / `UpdateEnv` → `HiddenKeyError`(ValueError 하위, `.keys`).
  `UpdateSetting` 은 모든 키를 먼저 검사해 하나라도 막히면 아무것도 적용하지 않는다.
  대상 스코프·버전 밖의 중첩 경로(`USER` 대상일 때 `sandbox.bwrapPath` 등)를 값 안에 끼워 넣는 것도 막는다.
  스키마 밖 키는 `Category.OTHER` 가 노출될 때만 허용.
- `setSettings` / `SetSetting` / JSON 페이지 "적용": 노출되지 않은 키는 **현재 보존값과 동일할 때만** 허용하고,
  바꾸거나 빼면 거부한다. `clear()` 도 보존값은 건드리지 않는다.
- `loadFile()` (또는 `setSettings(..., trusted=True)`)만 신뢰 소스로 취급해 숨긴 키를 새 보존값으로 받아들인다.
- 문자열 파싱: `Category.parse("model|hooks,ENV")`. 데모: `python -m qclaudecodesettingeditorwidget --categories "MODEL|HOOKS|ENV"` 또는 `--exclude "ADMIN|JSON"`.

## 편집 대상 스코프와 Claude Code 버전 필터

문서의 Scope 열은 키마다 효력이 있는 파일을 정한다(Any file 120 · Managed 34 · User or managed 20 · User/local/managed 4 ·
Global config 6). `targetScope` 로 **지금 편집하는 파일**을 정하면 그 파일에서 효력이 없는 키를 숨긴다.

```python
from qclaudecodesettingeditorwidget import QClaudeCodeSettingEditorWidget, Scope

w = QClaudeCodeSettingEditorWidget()                                  # 기본 USER: ~/.claude/settings.json
w = QClaudeCodeSettingEditorWidget(targetScope=Scope.PROJECT)         # .claude/settings.json — User or managed 키도 숨김
w = QClaudeCodeSettingEditorWidget(targetScope=Scope.MANAGED)         # 관리형 설정
w = QClaudeCodeSettingEditorWidget(targetScope=Scope.ANY_FILE)        # 설정 파일 4종 중 어디서든 효력 있는 키 전부
w = QClaudeCodeSettingEditorWidget(targetVersion="2.1.250")           # 2.1.250 에 없는 키(이후 추가·이전 제거) 숨김
w.setTargetScope(Scope.USER | Scope.PROJECT); w.setTargetVersion(None); w.inapplicableKeys()
```

- 플래그를 조합하면 그중 **하나라도** 효력이 있는 키를 보인다. `GLOBAL_CONFIG`(`~/.claude.json` 전용 키)는 settings.json 이
  아니므로 대상으로 줄 수 없고(ValueError) 항상 숨긴다.
- 버전은 `since`/`removed` 로 거른다. 버전 정보가 없는 키는 오래전부터 있던 것으로 보고 **항상 표시**한다.
  deprecated 키는 숨기지 않고 배지로 알린다.
- 중첩 키(`sandbox.bwrapPath`, `autoMode.classifyAllShell` 등)도 같은 규칙으로 숨긴다.
- 행 머리 배지: 스코프(`managed`, `user · managed`), 도입 버전(`v2.1.283+`), `deprecated`, `removed v2.1.277`.
- 숨긴 키의 값은 로드 시 그대로 보존되어 출력에 남는다(카테고리 제외와 같은 규칙).
- 데모: `python -m qclaudecodesettingeditorwidget --scope PROJECT --target-version 2.1.250` (하단 콤보·입력란으로도 전환).

## 동작 규칙

- **지연 구축**: 생성 시에는 내비게이션·키 메타·JSON 페이지만 만들고, 카테고리 페이지와 env 편집기는
  좌측에서 처음 선택되거나 `rowFor()`/`envEditor()`로 필요해질 때 만든다(생성 ~800 ms → ~30 ms).
  구축 전 값은 내부 `_pending` 에 보관되므로 `settings()`/`setSettings()`/`UpdateSetting()` 등의 의미는
  구축 여부와 무관하게 같다. 전부 즉시 구축하려면 `ensureAllPagesBuilt()`. 벤치: `python tools/bench_construct.py`.

- **포함/해제**: 각 키 앞의 체크박스가 "JSON에 포함" 여부. 해제된 키는 출력에 나오지 않는다.
  체크가 꺼진 편집기를 만지면 자동으로 켜진다. `required` 키는 항상 포함.
- **anyOf / oneOf**: 변형 선택 콤보 + 스택 편집기. 값을 로드하면 `value_matches` 휴리스틱으로
  맞는 변형을 자동 선택하고, 어느 변형에도 안 맞으면 `(raw JSON)` 로 떨어져 값을 보존한다.
  변형이 전부 문자열(`theme` 의 enum | `custom:*`)이면 제안 목록이 달린 편집 가능한 콤보 하나로 합친다.
  `type: [X, "null"]` 은 `null` 체크박스 + X 편집기.
- **스키마에 없는 키**는 그대로 보존해 다시 내보낸다(최상위·중첩 객체 모두).
- **env**: 스키마 340개 + 문서 전용 변수 100개 + overrides 1개 = 441개를 표로 제공. enum 이 있으면 콤보(직접 입력도 가능),
  문서에서 "Set to 1" 류로 추론된 값은 힌트로만 제공. 목록에 없는 변수는 `+ 사용자 변수` 로 추가.
- **JSON 페이지**: 현재 설정의 JSON 을 보여주고, 직접 고쳐 `JSON 적용` 으로 폼에 반영할 수 있다.
- **설정 키 ↔ env 변수 겹침**: `resources/overlaps.json`(문서에서 추출, 46개 설정 / 63쌍)을 바탕으로
  설정 행에 `관련 env: ANTHROPIC_MODEL (env 우선)` 링크(클릭 시 env 페이지로 이동·필터), env 행에 `↔ model` 접두어를 표시한다.
  둘 다 설정되어 있으면 툴바에 `⚠ 겹침 n건` 경고가 뜨고 `overlaps()` 로 목록을 얻을 수 있다.
  우선순위(`env`/`setting`)는 문서 문장에 명시된 경우에만 붙고, 나머지는 `related`(관련) 로 표시한다.

## 현지화 (Qt QTranslator / .ts / .qm)

소스 문자열은 영어이고, 번역은 Qt 표준 방식으로 붙는다.

- 파일: `qclaudecodesettingeditorwidget/locales/qccse_<lang>.ts` (Qt Linguist XML) 와 컴파일본 `qccse_<lang>.qm`.
  같은 디렉터리에 둘 다 있으면 `.qm` 을, 없으면 `.ts` 를 직접 읽는다(컴파일 불필요).
  **파일 하나만 두면 그 언어를 쓸 수 있다.** 내장: `en`(소스), `ko`.
- 검색 디렉터리(뒤가 우선): 패키지 `locales/` → 환경변수 `QCCSE_LOCALE_DIR`(`os.pathsep` 구분) → `i18n.add_locale_dir()`.
- 언어 선택: `QClaudeCodeSettingEditorWidget(language="ko")`, `setLanguage("ko")`, 환경변수 `QCCSE_LANG`,
  아니면 시스템 로케일(`ko_KR` → `ko`), 최종 `en`.
- 컨텍스트 두 개:
  - `qccse` — UI 문자열. 소스는 영어 원문(`Open…`). `_name` 항목이 언어 표시 이름.
  - `schema` — 스키마 설명. 소스는 설정 경로(`permissions.allow`, `hooks.PreToolUse[].matcher`, `env.API_TIMEOUT_MS`).
    번역이 없으면 스키마의 영어 description 을 그대로 쓴다. `<extracomment>` 에 영어 원문이 들어 있어 Linguist 에서 참고할 수 있다.

```bash
python tools/build_translations.py --lang ja          # 새 언어 .ts 생성 (Linguist 로 번역)
python tools/build_translations.py                    # 소스 변경 후 기존 .ts 갱신 (번역 보존, 새 항목 unfinished)
python tools/build_translations.py --import ja qccse=ja_ui.json schema=ja_desc.json   # {source: translation} JSON 반영
python tools/build_translations.py --compile          # pyside6-lrelease 로 .qm 생성
```

## 리소스 갱신

Claude Code 가 새 버전을 내면 다음으로 번들 리소스·생성 코드를 다시 만든다(네트워크 필요).

```bash
python tools/refresh_resources.py              # 로컬 파일로: --schema/--envdoc/--settingsdoc/--changelog PATH
python tools/build_translations.py             # 새 경로가 .ts 에 unfinished 로 추가된다
python tools/build_translations.py --compile
```

| 출처 | 쓰임 |
| --- | --- |
| [settings-reference.md](https://code.claude.com/docs/en/settings-reference.md) | **1차 출처**: 키 목록·Scope·Type·Default·`Requires Claude Code vX`·Deprecated/Removed |
| [schemastore claude-code-settings.json](https://www.schemastore.org/claude-code-settings.json) | 키별 상세 JSON 구조(문서에 없는 키의 관리형 판별은 설명 문구로) |
| [env-vars.md](https://code.claude.com/docs/en/env-vars.md) | env 변수 설명·값 힌트 |
| [CHANGELOG.md](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md) | 최신 버전(= 패키지 버전), 문서에 없는 키의 `since`("Added `key` setting") |
| `tools/resource_overrides.json` (손 관리) | 생성 결과 위에 덮어쓰는 보정: 구조를 추론할 수 없는 객체 키의 스키마, 문서에 없는 env 변수 등 |
| `tools/settings_history.json` (자동 관리) | 갱신 때마다 문서에 보인 버전 범위 — 이후 새로 생긴 키의 `since`, 문서에서 사라진 키의 `removed` |

- 생성물: `resources/` 의 병합 스키마·`env-vars.json`·`overlaps.json`, `keys.py`, `env_keys.py`, `_version.py`.
- `since` 우선순위: overrides > 문서 > CHANGELOG > 이력. `removed`/`deprecated`: overrides > 문서 > 이력.
- 문서에만 있는 키는 Type 문장(Boolean, 문자열 enum, 숫자 범위, 문자열 배열)에서 스키마를 만들고, 객체형은 overrides 에 적는다.
  `Global config` 전용 키는 settings.json 이 아니므로 주입하지 않는다.
- 새로 생긴 최상위 키는 `categories.py` 에 분류가 없어도 `Other` 페이지에 자동으로 나타난다.
- 문서에 새 주제(Topic 열)가 생기면 갱신이 멈추고 `constants.Topic` 에 추가하라고 알린다.

## 구조

```
qclaudecodesettingeditorwidget/
├── widget.py          # QClaudeCodeSettingEditorWidget (툴바·내비게이션·지연 구축·필터, 값 보관처)
├── widget_api.py      # SettingsApiMixin: settings/setSettings/Update*/단건 접근·노출 정책, HiddenKeyError
├── pages.py           # KeyMeta(행 없이 검색·스코프/버전 판별)와 지연 구축 _Page
├── demo.py            # 테스트 메인윈도우 (언어 선택, 확인 → JSON 표시)
├── env_editor.py      # EnvEditor: env 변수 표
├── i18n.py            # QTranslator 로딩, .ts 직접 로더(TsTranslator), tr()/describe()
├── editors/
│   ├── __init__.py    # create_editor 팩토리 (스키마 노드 → 편집기)
│   ├── base.py        # BaseEditor
│   ├── badges.py      # SettingInfo → 스코프·since·deprecated·removed 배지
│   ├── scalars.py     # String / Enum / Bool / Int / Number / Const / Null
│   └── containers.py  # PropertyRow / Object / Dict / StringList / CheckList / List / AnyOf / Nullable / RawJson
├── schema.py          # 스키마 로딩, $ref, value_matches, 중첩 경로 적용 검사, env 레지스트리
├── categories.py      # 최상위 키 → 카테고리 (영어 제목이 번역 소스, 키는 SettingKey)
├── constants.py       # 전역 참조 상수: Scope·JsonType(비트 플래그), Topic·Precedence, 페이지 id, 리소스·번역 이름, 공용 스타일
├── spec.py            # Version, SettingInfo(dataclass), KeyEnum
├── keys.py            # SettingKey(멤버 값 = SettingInfo) + NESTED_SETTINGS + setting_info() (자동 생성)
├── env_keys.py        # EnvVar enum (자동 생성)
├── _version.py        # 패키지 버전 = Claude Code 버전 (자동 생성)
├── locales/           # qccse_ko.ts / qccse_ko.qm
└── resources/         # claude-code-settings.schema.json(병합), env-vars.json, overlaps.json
tools/
├── refresh_resources.py    # 문서·스키마·CHANGELOG 다운로드 → resources/, keys.py·env_keys.py·_version.py 생성
├── refresh/                # pkg(패키지 모듈 로더) / markdown(문서 파서) / changelog / catalog(스코프·버전·스키마 주입) /
│                           # envvars / overlaps / codegen
├── resource_overrides.json # 손 보정 (객체 키 스키마, 문서에 없는 env 변수 …)
├── settings_history.json   # 문서에 보인 버전 범위 (자동)
├── bench_construct.py      # 위젯 생성 시간 벤치
└── build_translations.py   # .ts 생성/갱신/가져오기/컴파일
```
