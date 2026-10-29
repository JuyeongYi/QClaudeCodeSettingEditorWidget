"""번들 리소스·생성 코드 갱신 스크립트.

출처 (공식 문서가 1차, schemastore 는 키별 상세 JSON 구조 보충용)
- https://code.claude.com/docs/en/settings-reference.md → 키 목록·스코프·타입·기본값·since/deprecated/removed
- https://www.schemastore.org/claude-code-settings.json → 스키마 기반 (문서에만 있는 키는 Type 문장에서 주입)
- https://code.claude.com/docs/en/env-vars.md            → env 변수 설명
- https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md → 최신 버전, 'Added `key` setting' 버전
- tools/resource_overrides.json (손으로 관리) → 키·경로·env 보정, 구조를 추론할 수 없는 키의 스키마
- tools/settings_history.json   (자동 관리)   → 문서에 보인 버전 범위(새 키의 since, 사라진 키의 removed)

생성물
- resources/claude-code-settings.schema.json (병합 스키마), resources/env-vars.json, resources/overlaps.json
- keys.py (SettingKey + NESTED_SETTINGS), env_keys.py (EnvVar), _version.py (= Claude Code 최신 버전)

사용법: python tools/refresh_resources.py [--schema PATH] [--envdoc PATH] [--settingsdoc PATH] [--changelog PATH]
(PATH를 주면 네트워크 대신 로컬 파일을 사용)
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

from refresh.catalog import build_catalog, update_history
from refresh.changelog import added_versions, latest_version
from refresh.codegen import write_env_keys_module, write_keys_module, write_version_module
from refresh.envvars import build_env_registry
from refresh.markdown import parse_env_doc, parse_settings_reference
from refresh.overlaps import build_overlaps
from refresh.pkg import ENV_KEY, PKG, Version, constants

SCHEMA_URL = "https://www.schemastore.org/claude-code-settings.json"
ENV_DOC_URL = "https://code.claude.com/docs/en/env-vars.md"
SETTINGS_DOC_URL = "https://code.claude.com/docs/en/settings-reference.md"
CHANGELOG_URL = "https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md"

RES = PKG / constants.RESOURCE_DIR
SCHEMA_OUT = RES / constants.SCHEMA_RESOURCE
ENV_OUT = RES / constants.ENV_RESOURCE
OVERLAPS_OUT = RES / constants.OVERLAPS_RESOURCE
OVERRIDES = Path(__file__).resolve().parent / "resource_overrides.json"
HISTORY = Path(__file__).resolve().parent / "settings_history.json"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "QClaudeCodeSettingEditorWidget/refresh"})
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
        return resp.read().decode("utf-8")


def _read(path: str | None, url: str) -> str:
    return Path(path).read_text("utf-8") if path else fetch(url)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text("utf-8")) if path.exists() else {}


def _dump(path: Path, data: object, indent: int) -> None:
    path.write_text(json.dumps(data, indent=indent, ensure_ascii=False) + "\n", "utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--schema", help="로컬 스키마 JSON 경로(네트워크 대신 사용)")
    ap.add_argument("--envdoc", help="로컬 env-vars.md 경로")
    ap.add_argument("--settingsdoc", help="로컬 settings-reference.md 경로")
    ap.add_argument("--changelog", help="로컬 CHANGELOG.md 경로")
    args = ap.parse_args(argv)

    store = json.loads(_read(args.schema, SCHEMA_URL))
    env_md = _read(args.envdoc, ENV_DOC_URL)
    settings_md = _read(args.settingsdoc, SETTINGS_DOC_URL)
    changelog_md = _read(args.changelog, CHANGELOG_URL)

    version = latest_version(changelog_md)
    if version is None:
        raise SystemExit("CHANGELOG 에서 버전을 찾지 못했다")
    docs = parse_settings_reference(settings_md)
    overrides = _load_json(OVERRIDES)
    old_history = _load_json(HISTORY)
    if old_history.get("paths") and max(Version.parse(r["lastSeen"]) for r in old_history["paths"].values()) > \
            Version.parse(version):
        raise SystemExit(f"이력이 {version} 보다 새 버전을 담고 있다 — 오래된 문서로 갱신하려는지 확인")
    history = update_history(old_history, list(docs), version)
    added = added_versions(changelog_md, set(docs) | set(store.get("properties", {})))

    schema, top, nested, notes = build_catalog(store, docs, added, history, overrides.get("settings", {}))
    RES.mkdir(parents=True, exist_ok=True)
    _dump(SCHEMA_OUT, schema, 2)
    registry = build_env_registry(schema, parse_env_doc(env_md), overrides.get(ENV_KEY, {}))
    _dump(ENV_OUT, registry, 1)
    overlaps = build_overlaps(schema, env_md, settings_md)
    _dump(OVERLAPS_OUT, overlaps, 1)
    write_keys_module(top, nested, version)
    write_env_keys_module(sorted(registry))
    write_version_module(version)
    _dump(HISTORY, history, 1)

    injected = [k for k, i in top.items() if not i["in_schemastore"]]
    print(f"Claude Code v{version} → _version.py")
    print(f"docs: {len(docs)} entries ({sum('.' not in p for p in docs)} top-level)")
    print(f"schema: {len(top)} top-level keys (schemastore {len(store.get('properties', {}))}, "
          f"+{len(injected)} from docs) → {SCHEMA_OUT.name}")
    print(f"keys.py: SettingKey {len(top)} (since {sum(bool(i['since']) for i in top.values())}, "
          f"deprecated {sum(i['deprecated'] for i in top.values())}, removed {sum(bool(i['removed']) for i in top.values())})"
          f" / NESTED_SETTINGS {len(nested)}")
    print(f"env: {len(registry)} variables → {ENV_OUT.name}, env_keys.py")
    print(f"overlaps: {len(overlaps)} settings / {sum(len(v) for v in overlaps.values())} pairs → {OVERLAPS_OUT.name}")
    for n in notes:
        print(f"  note: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
