"""update-claude-code-version 스킬 보조 점검 (프로젝트 루트에서 `python -X utf8 <this> <command>`).

  changelog OLD NEW CHANGELOG.md   OLD 초과 ~ NEW 이하 CHANGELOG 항목이 언급한 env 변수·설정 키 중 번들에 없는 것
  obsolete                         더 이상 필요 없는 보정·매핑·번역 (제거 후보)
  translations OUT.json            번역할 schema 항목(새 항목·영어 원문이 바뀐 항목)을 {source: {en, current}} 로 저장
  stats                            README 에 적힌 버전·개수의 현재 값

refresh_resources.py → build_translations.py 를 돌린 뒤에 쓴다. 판단(추가·제거)은 사람이/Claude 가 한다.
"""
from __future__ import annotations

import collections
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from refresh_resources import HISTORY, OVERRIDES  # noqa: E402
from refresh.pkg import PKG  # noqa: E402

from qclaudecodesettingeditorwidget import NESTED_SETTINGS, SettingKey, Version, __version__  # noqa: E402
from qclaudecodesettingeditorwidget.categories import CATEGORIES  # noqa: E402
from qclaudecodesettingeditorwidget.constants import (  # noqa: E402
    CONTEXT_SCHEMA, ENV_KEY, ENV_RESOURCE, LOCALE_DIR, OVERLAPS_RESOURCE, RESOURCE_DIR,
)

_ENV_TOKEN = re.compile(r"`([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)(?:=[^`]*)?`")
_SETTING_TOKEN = re.compile(r"`([a-z][A-Za-z0-9]*(?:\.[A-Za-z0-9]+)*)`(?: \w+)? setting")


def _json(path: Path) -> dict:
    return json.loads(path.read_text("utf-8")) if path.exists() else {}


def _env_registry() -> dict[str, dict]:
    return _json(PKG / RESOURCE_DIR / ENV_RESOURCE)


def _setting_paths() -> set[str]:
    return {k.value for k in SettingKey} | set(NESTED_SETTINGS)


def cmd_changelog(old: str, new: str, changelog: str) -> None:
    lo, hi = Version.parse(old), Version.parse(new)
    env, settings = _env_registry(), _setting_paths()
    current: Version | None = None
    for line in Path(changelog).read_text("utf-8").splitlines():
        if line.startswith("## "):
            try:
                current = Version.parse(line[3:].strip())
            except ValueError:
                current = None
            continue
        if current is None or not (lo < current <= hi):
            continue
        missing_env = [v for v in _ENV_TOKEN.findall(line) if v not in env]
        missing_set = [k for k in _SETTING_TOKEN.findall(line) if k not in settings]
        if missing_env or missing_set:
            print(f"[{current}] env={missing_env} settings={missing_set}\n    {line.strip()[:220]}")


def cmd_obsolete() -> None:
    overrides, env = _json(OVERRIDES), _env_registry()
    settings, history = _setting_paths(), _json(HISTORY).get("paths", {})
    found = 0

    def report(msg: str) -> None:
        nonlocal found
        found += 1
        print(msg)

    for name in overrides.get(ENV_KEY, {}):
        info = env.get(name)
        if info is None:
            report(f"overrides.env.{name}: 레지스트리에 없음 → 제거")
        elif info.get("inDocs") or info.get("inSchema"):
            report(f"overrides.env.{name}: 이제 공식 {'문서' if info.get('inDocs') else '스키마'}에 있음 → 보정 제거"
                   " (값 후보 등 문서로 안 되는 보정만 남길 것)")
    for path, ov in overrides.get("settings", {}).items():
        if path not in settings and path not in history:
            report(f"overrides.settings.{path}: 문서·스키마·이력 어디에도 없음 → 제거")
            continue
        top = path.split(".")[0]
        info = NESTED_SETTINGS.get(path) or (SettingKey[top].info if top in SettingKey.__members__ else None)
        if "schema" in ov and info is not None and info.in_schemastore and info.key == path:
            report(f"overrides.settings.{path}: schemastore 가 이제 스키마를 제공 → 주입한 schema 가 아직 필요한지 검토")
    categorized = [k for _, ks in CATEGORIES for k in ks]
    for key, n in collections.Counter(categorized).items():
        if n > 1:
            report(f"categories.py: {key.value} 가 {n}개 카테고리에 중복 → 하나만 남김")
    uncategorized = [k.value for k in SettingKey if k not in set(categorized) and k.value != ENV_KEY]
    if uncategorized:
        report(f"categories.py: 미분류(Other 페이지) {uncategorized} → 알맞은 카테고리에 추가")
    for ts in sorted((PKG / LOCALE_DIR).glob("*.ts")):
        vanished = sum(1 for t in ET.parse(ts).getroot().iter("translation") if t.get("type") in ("vanished", "obsolete"))
        if vanished:
            report(f"{ts.name}: vanished/obsolete 번역 {vanished}건 → build_translations.py(--keep-vanished 없이)로 제거")
    overlaps = _json(PKG / RESOURCE_DIR / OVERLAPS_RESOURCE)
    for key, pairs in overlaps.items():
        for p in pairs:
            if p["env"] not in env:
                report(f"overlaps.json: {key} ↔ {p['env']} 의 env 변수가 레지스트리에 없음 → overlaps 추출 확인")
    print(f"제거·정리 후보 {found}건" if found else "제거·정리 후보 없음")


def cmd_translations(out: str) -> None:
    todo: dict[str, dict[str, str]] = {}
    for ts in sorted((PKG / LOCALE_DIR).glob("*.ts")):
        for ctx in ET.parse(ts).getroot().iter("context"):
            if ctx.findtext("name") != CONTEXT_SCHEMA:
                continue
            for msg in ctx.iter("message"):
                tr = msg.find("translation")
                if tr is not None and tr.get("type") == "unfinished":
                    todo[f"{ts.stem}:{msg.findtext('source')}"] = {
                        "en": msg.findtext("extracomment") or "", "current": tr.text or ""}
    Path(out).write_text(json.dumps(todo, indent=1, ensure_ascii=False) + "\n", "utf-8")
    print(f"{len(todo)}건 → {out} (키는 '<ts 파일 stem>:<source>', current 가 있으면 원문이 바뀐 기존 번역)")


def cmd_stats() -> None:
    env = _env_registry()
    overlaps = _json(PKG / RESOURCE_DIR / OVERLAPS_RESOURCE)
    in_schema = sum(v["inSchema"] for v in env.values())
    docs_only = sum(v["inDocs"] and not v["inSchema"] for v in env.values())
    print(f"version {__version__}")
    print(f"SettingKey {len(SettingKey)} / NESTED_SETTINGS {len(NESTED_SETTINGS)}")
    print(f"env: 스키마 {in_schema}개 + 문서 전용 변수 {docs_only}개 + overrides {len(env) - in_schema - docs_only}개"
          f" = {len(env)}개")
    print(f"overlaps: {len(overlaps)}개 설정 / {sum(len(v) for v in overlaps.values())}쌍")
    scopes = collections.Counter(k.info.scope for k in SettingKey if k.info is not None)
    print("scope: " + " · ".join(f"{s.name or repr(s)} {n}" for s, n in scopes.most_common()))
    readme = (ROOT / "README.md").read_text("utf-8")
    stale = sorted(set(re.findall(r"현재 `?(\d+\.\d+\.\d+)", readme)) - {__version__})
    print(f"README 의 낡은 '현재 버전' 표기: {stale}" if stale else "README 의 '현재 버전' 표기 최신")


def main(argv: list[str]) -> int:
    commands = {"changelog": (cmd_changelog, 3), "obsolete": (cmd_obsolete, 0),
                "translations": (cmd_translations, 1), "stats": (cmd_stats, 0)}
    if not argv or argv[0] not in commands or len(argv) - 1 != commands[argv[0]][1]:
        print(__doc__)
        return 2
    fn, _ = commands[argv[0]]
    fn(*argv[1:])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
