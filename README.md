# QClaudeCodeSettingEditorWidget

Claude Code `settings.json` 의 **모든 키**를 GUI로 편집하는 PySide6 위젯.
[schemastore 의 claude-code-settings.json](https://www.schemastore.org/claude-code-settings.json) 스키마를
번들해 두고, 그 스키마로부터 편집기를 자동 생성한다. `env` 는 스키마의 변수 목록에
[환경 변수 문서](https://code.claude.com/docs/en/env-vars)를 병합한 전용 표로 편집한다.

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
| `showManagedOnly()` / `setShowManagedOnly(bool)` / `managedOnlyKeys()` | 관리형 전용 키 표시 여부 (생성자 `showManagedOnly=False`) |
| `settingChanged` (Signal) | 값이 바뀔 때마다 (같은 이벤트 루프 턴 내 변경은 한 번으로 합침) |

## 키 enum 과 단건·JSON 갱신

키 문자열 대신 `keys.py` 의 enum 을 쓴다. `SettingKey`(최상위 설정 키 142개)와 `EnvVar`(환경변수 386개)는
`str` 겸용이라 **멤버 이름이 곧 키**다: `SettingKey.model == "model"`, `EnvVar.API_TIMEOUT_MS == "API_TIMEOUT_MS"`.
식별자가 될 수 없는 `$schema` 만 `SettingKey.schema`(값 `"$schema"`)다. 위젯 내부(카테고리 표 등)도 이 enum 을 쓴다.
`tools/refresh_resources.py` 가 스키마·문서에서 다시 생성하며, 테스트가 스키마와의 동기화를 검사한다.

```python
from qclaudecodesettingeditorwidget import EnvVar, SettingKey

w.setSettingValue(SettingKey.model, "opus");  w.settingValue(SettingKey.model);  w.unsetSetting(SettingKey.model)
w.setEnvValue(EnvVar.API_TIMEOUT_MS, "1200000");  w.envValue(EnvVar.API_TIMEOUT_MS)

w.UpdateSetting('{"effortLevel": "high", "fastMode": null}')   # 설정 병합: null 이면 해제, 결과 settings() 반환
w.UpdateEnv('{"API_TIMEOUT_MS": "1200000", "DEBUG": null}')     # env 병합: null 이면 해제, 결과 env dict 반환
w.UpdateEnv("{}", replace={"ONLY": "this"})                     # env 전체 교체
```

`UpdateSetting` / `UpdateEnv` 는 JSON 문자열과 dict 를 모두 받고, 키는 문자열·enum 멤버·멤버 이름(`"schema"`) 어느 것이든 된다.
노출되지 않은 키(숨긴 카테고리·관리형 전용·env 페이지 없음)는 읽기(`settingValue`/`envValue`)만 되고 갱신하면 `HiddenKeyError` 다(아래 우회 방지 정책).

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
| `OTHER` | 스키마 갱신으로 새로 생겨 분류되지 않은 키 |
| `ENV` / `JSON` | 환경 변수 페이지 / JSON 페이지 |
| `SETTINGS` | 위 설정 카테고리 전부 (`ENV`·`JSON` 제외) |
| `ALL` / `NONE` | 전부 / 없음 |

- 제외된 카테고리는 페이지가 아예 만들어지지 않으며 `rowFor(key)` 는 `None`, `Category.ENV` 가 없으면 `envEditor()` 도 `None`.
- 제외된 카테고리에 속한 키가 **파일에서 로드**되면 편집 불가 상태로 보존되어 `settings()`/`GetSetting()` 에 그대로 다시 나온다(값 유실 방지).
  숨긴 키까지 출력에서 빼려면 호출 측에서 걸러낸다. JSON 페이지가 켜져 있으면 그 JSON 에는 보존된 키가 보인다.

### 우회 방지 정책

생성자에서 정한 노출 범위(카테고리·`showManagedOnly`·env 페이지)는 함수 API 로도 넘을 수 없다. `isKeyExposed(key)` 가 False 인 키는:

- `setSettingValue` / `unsetSetting` / `UpdateSetting` / `setEnvValue` / `UpdateEnv` → `HiddenKeyError`(ValueError 하위, `.keys`).
  `UpdateSetting` 은 모든 키를 먼저 검사해 하나라도 막히면 아무것도 적용하지 않는다.
  `showManagedOnly=False` 면 중첩 관리형 경로(`sandbox.enabledPlatforms` 등)를 값 안에 끼워 넣는 것도 막는다.
  스키마 밖 키는 `Category.OTHER` 가 노출될 때만 허용.
- `setSettings` / `SetSetting` / JSON 페이지 "적용": 노출되지 않은 키는 **현재 보존값과 동일할 때만** 허용하고,
  바꾸거나 빼면 거부한다. `clear()` 도 보존값은 건드리지 않는다.
- `loadFile()` (또는 `setSettings(..., trusted=True)`)만 신뢰 소스로 취급해 숨긴 키를 새 보존값으로 받아들인다.
- 문자열 파싱: `Category.parse("model|hooks,ENV")`. 데모: `python -m qclaudecodesettingeditorwidget --categories "MODEL|HOOKS|ENV"` 또는 `--exclude "ADMIN|JSON"`.

## 관리형(managed) 전용 키 숨기기

`(Managed settings only)`, `Only honored from managed (policy) settings` 처럼 스키마 설명이 관리형(정책) 설정에서만
유효하다고 밝힌 키는 기본적으로 **숨긴다**. 중첩 키(`sandbox.enabledPlatforms` 등)도 포함되며, 보이는 키에는 `managed` 배지가 붙는다.

```python
w = QClaudeCodeSettingEditorWidget()                        # showManagedOnly=False: 관리형 전용 키 숨김
w = QClaudeCodeSettingEditorWidget(showManagedOnly=True)    # 전부 표시
w.setShowManagedOnly(True); w.showManagedOnly(); w.managedOnlyKeys()
```

숨긴 키의 값은 로드 시 그대로 보존되어 출력에 남는다(카테고리 제외와 같은 규칙). 판별은 `schema.is_managed_only()`.
데모: `python -m qclaudecodesettingeditorwidget --show-managed`.

## 동작 규칙

- **포함/해제**: 각 키 앞의 체크박스가 "JSON에 포함" 여부. 해제된 키는 출력에 나오지 않는다.
  체크가 꺼진 편집기를 만지면 자동으로 켜진다. `required` 키는 항상 포함.
- **anyOf / oneOf**: 변형 선택 콤보 + 스택 편집기. 값을 로드하면 `value_matches` 휴리스틱으로
  맞는 변형을 자동 선택하고, 어느 변형에도 안 맞으면 `(raw JSON)` 로 떨어져 값을 보존한다.
  변형이 전부 문자열(`theme` 의 enum | `custom:*`)이면 제안 목록이 달린 편집 가능한 콤보 하나로 합친다.
  `type: [X, "null"]` 은 `null` 체크박스 + X 편집기.
- **스키마에 없는 키**는 그대로 보존해 다시 내보낸다(최상위·중첩 객체 모두).
- **env**: 스키마 340개 + 문서 전용 변수 46개 = 386개를 표로 제공. enum 이 있으면 콤보(직접 입력도 가능),
  문서에서 "Set to 1" 류로 추론된 값은 힌트로만 제공. 목록에 없는 변수는 `+ 사용자 변수` 로 추가.
- **JSON 페이지**: 현재 설정의 JSON 을 보여주고, 직접 고쳐 `JSON 적용` 으로 폼에 반영할 수 있다.
- **설정 키 ↔ env 변수 겹침**: `resources/overlaps.json`(문서에서 추출, 29개 설정 / 40쌍)을 바탕으로
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

스키마와 문서가 바뀌면 다음으로 번들 리소스를 다시 만든다(네트워크 필요).

```bash
python tools/refresh_resources.py
python tools/build_translations.py --compile   # 새 경로가 .ts 에 unfinished 로 추가된다
```

새로 생긴 최상위 키는 `categories.py` 에 분류가 없어도 `Other` 페이지에 자동으로 나타난다.

## 구조

```
qclaudecodesettingeditorwidget/
├── widget.py          # QClaudeCodeSettingEditorWidget (툴바·카테고리·env·JSON 페이지, 공개 API)
├── demo.py            # 테스트 메인윈도우 (언어 선택, 확인 → JSON 표시)
├── env_editor.py      # EnvEditor: env 변수 표
├── i18n.py            # QTranslator 로딩, .ts 직접 로더(TsTranslator), tr()/describe()
├── editors/
│   ├── __init__.py    # create_editor 팩토리 (스키마 노드 → 편집기)
│   ├── base.py        # BaseEditor
│   ├── scalars.py     # String / Enum / Bool / Int / Number / Const / Null
│   └── containers.py  # PropertyRow / Object / Dict / StringList / CheckList / List / AnyOf / Nullable / RawJson
├── schema.py          # 스키마 로딩, $ref, value_matches, env 레지스트리
├── categories.py      # 최상위 키 → 카테고리 (영어 제목이 번역 소스, 키는 SettingKey)
├── keys.py            # SettingKey / EnvVar enum (자동 생성)
├── locales/           # qccse_ko.ts / qccse_ko.qm
└── resources/         # claude-code-settings.schema.json, env-vars.json
tools/
├── refresh_resources.py    # 스키마·env 문서 다운로드 → resources/
└── build_translations.py   # .ts 생성/갱신/가져오기/컴파일
```
