"""번들 리소스 갱신 스크립트.

- https://www.schemastore.org/claude-code-settings.json → resources/claude-code-settings.schema.json
- https://code.claude.com/docs/en/env-vars.md            → resources/env-vars.json (스키마 env + 문서 병합)
- + https://code.claude.com/docs/en/settings-reference.md → resources/overlaps.json (설정 키 ↔ env 변수 겹침)

사용법: python tools/refresh_resources.py [--schema PATH] [--envdoc PATH] [--settingsdoc PATH]
(PATH를 주면 네트워크 대신 로컬 파일을 사용)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

SCHEMA_URL = "https://www.schemastore.org/claude-code-settings.json"
ENV_DOC_URL = "https://code.claude.com/docs/en/env-vars.md"
SETTINGS_DOC_URL = "https://code.claude.com/docs/en/settings-reference.md"

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "qclaudecodesettingeditorwidget" / "resources"
SCHEMA_OUT = RES / "claude-code-settings.schema.json"
ENV_OUT = RES / "env-vars.json"
OVERLAPS_OUT = RES / "overlaps.json"

_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_ROW = re.compile(r"^\| `([^`]+)`\s*\|(.*)\|\s*$")
_ENV_NAME = re.compile(r"\b([A-Z][A-Z0-9_]{6,})\b")


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "QClaudeCodeSettingEditorWidget/refresh"})
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
        return resp.read().decode("utf-8")


def clean_markdown(text: str) -> str:
    text = _LINK.sub(r"\1", text)
    text = text.replace("`", "")
    return re.sub(r"\s+", " ", text).strip()


def parse_env_doc(markdown: str) -> dict[str, str]:
    """'## Variables' 절의 표(| `NAME` | Purpose |)를 {NAME: purpose}로 파싱."""
    rows: dict[str, str] = {}
    in_vars = False
    for line in markdown.splitlines():
        if line.startswith("## "):
            in_vars = line.strip().lower() == "## variables"
            continue
        if not in_vars:
            continue
        m = _ROW.match(line)
        if m:
            rows[m.group(1).strip()] = clean_markdown(m.group(2))
    return rows


def suggest_values(desc: str) -> list[str]:
    """문서 설명에서 값 힌트를 추론(불리언 성격의 변수)."""
    if re.search(r"\bset to (1|true)\b", desc, re.IGNORECASE):
        if re.search(r"\btrue\b", desc) and not re.search(r"\bset to 1\b", desc, re.IGNORECASE):
            return ["true", "false"]
        return ["1", "0"]
    return []


def build_env_registry(schema: dict, doc_rows: dict[str, str]) -> dict[str, dict]:
    env_props = schema.get("properties", {}).get("env", {}).get("properties", {})
    names = sorted(set(env_props) | set(doc_rows))
    out: dict[str, dict] = {}
    for name in names:
        prop = env_props.get(name, {})
        doc = doc_rows.get(name, "")
        entry: dict = {
            "description": doc or clean_markdown(prop.get("description", "")),
            "schemaDescription": prop.get("description", ""),
            "values": list(prop.get("enum", [])),
            "inSchema": name in env_props,
            "inDocs": name in doc_rows,
        }
        if not entry["values"]:
            entry["values"] = suggest_values(entry["description"])
            entry["valuesAreHints"] = bool(entry["values"])
        out[name] = entry
    return out


# --------------------------------------------------------------------------- 설정 ↔ env 겹침
def _sentences_about(text: str, needle: str) -> str:
    """text 에서 needle(대소문자 무시)이 들어간 문장만 이어 붙인다."""
    parts = re.split(r"(?<=[.!?])\s+", text)
    return " ".join(s for s in parts if needle.lower() in s.lower()).strip()


def _precedence(key: str, env: str, env_row: str, setting_body: str, env_first: set[str]) -> str:
    """문서 문장에 정확히 앵커된 규칙으로만 판정. 확신이 없으면 'related'."""
    k, e = re.escape(key), re.escape(env)
    env_wins = [
        rf"{e}\b[^.]{{0,80}}\b(?:takes precedence over|overrides|applies over|outranks)\b[^.]{{0,40}}\b{k}\b",
        rf"\b(?:takes precedence over|overrides|applies over)\b[^.]{{0,40}}\b{k}\b[^.]{{0,20}}(?:setting|key)",
        rf"\b{k}\b[^.]{{0,60}}\b(?:only when|unless)\b[^.]{{0,40}}\b{e}\b[^.]{{0,20}}\b(?:is )?(?:unset|not set)",
    ]
    setting_wins = [
        rf"(?:value here|this key|this setting|the {k} (?:key|setting))[^.]{{0,60}}\b(?:outranks|takes precedence over|applies over|overrides)\b[^.]{{0,40}}\b{e}\b",
        rf"\b{e}\b[^.]{{0,80}}\b(?:only when|unless)\b[^.]{{0,40}}(?:no (?:settings )?file sets|nothing else selects|\b{k}\b[^.]{{0,20}}(?:is )?(?:unset|not set))",
    ]
    text = " ".join([env_row, setting_body])
    if env in env_first or any(re.search(p, text, re.I) for p in env_wins):
        return "env"
    if any(re.search(p, text, re.I) for p in setting_wins):
        return "setting"
    return "related"


def build_overlaps(schema: dict, env_md: str, settings_md: str) -> dict[str, list[dict]]:
    """설정 키 → [{env, precedence: env|setting|related, note}]. 세 출처의 합집합.

    1) env 문서 행의 settings-reference#anchor 링크
    2) 스키마 설정 description 이 언급하는 env 이름
    3) settings-reference 문서에서 각 설정 절이 언급하는 env 이름
    """
    keys = {k.lower(): k for k in schema.get("properties", {}) if k != "env"}
    envs = set(schema.get("properties", {}).get("env", {}).get("properties", {}))
    env_rows: dict[str, str] = {}
    for line in env_md.splitlines():
        m = _ROW.match(line)
        if m and re.fullmatch(r"[A-Z0-9_]+", m.group(1).strip()):
            env_rows[m.group(1).strip()] = clean_markdown(m.group(2))
    envs |= set(env_rows)
    # "For ANTHROPIC_MODEL and CLAUDE_CODE_AUTO_CONNECT_IDE, Claude Code reads the variable first ..."
    env_first: set[str] = set()
    for m in re.finditer(r"For ((?:[A-Z][A-Z0-9_]+(?:,? (?:and )?)?)+), Claude Code reads the variable first",
                         env_md.replace("`", "")):
        env_first |= set(re.findall(r"[A-Z][A-Z0-9_]+", m.group(1)))
    setting_bodies: dict[str, str] = {}
    pairs: dict[str, dict[str, str]] = {}  # setting -> env -> note

    def add(setting: str, env: str, note: str) -> None:
        bucket = pairs.setdefault(setting, {})
        if len(note) > len(bucket.get(env, "")):
            bucket[env] = note
        bucket.setdefault(env, "")

    for env, desc in env_rows.items():
        for anchor in re.findall(r"settings-reference#([a-z0-9-]+)", desc):
            key = keys.get(anchor.replace("-", ""))
            if key:
                add(key, env, _sentences_about(desc, key))

    for key, prop in schema.get("properties", {}).items():
        if key == "env":
            continue
        desc = clean_markdown(prop.get("description", ""))
        for name in set(_ENV_NAME.findall(desc)):
            if name in envs:
                add(key, name, _sentences_about(desc, name))

    for sec in re.split(r"^#{2,4} ", settings_md, flags=re.M):
        title = sec.split("\n", 1)[0].strip().strip("`")
        key = keys.get(title.lower().replace("-", ""))
        if not key:
            continue
        body = clean_markdown(re.sub(r"theme=\{null\}|\*\*|^\s*\*\s+", " ", sec, flags=re.M))
        setting_bodies[key] = body
        for name in set(_ENV_NAME.findall(body)):
            if name in envs:
                add(key, name, _sentences_about(body, name))

    out: dict[str, list[dict]] = {}
    for key in sorted(pairs):
        entries = []
        for env, note in sorted(pairs[key].items()):
            prec = _precedence(key, env, env_rows.get(env, ""), setting_bodies.get(key, ""), env_first)
            entries.append({"env": env, "precedence": prec, "note": note[:400]})
        out[key] = entries
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--schema", help="로컬 스키마 JSON 경로(네트워크 대신 사용)")
    ap.add_argument("--envdoc", help="로컬 env-vars.md 경로(네트워크 대신 사용)")
    ap.add_argument("--settingsdoc", help="로컬 settings-reference.md 경로(네트워크 대신 사용)")
    args = ap.parse_args(argv)

    schema_text = Path(args.schema).read_text("utf-8") if args.schema else fetch(SCHEMA_URL)
    env_md = Path(args.envdoc).read_text("utf-8") if args.envdoc else fetch(ENV_DOC_URL)
    settings_md = Path(args.settingsdoc).read_text("utf-8") if args.settingsdoc else fetch(SETTINGS_DOC_URL)

    schema = json.loads(schema_text)
    RES.mkdir(parents=True, exist_ok=True)
    SCHEMA_OUT.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", "utf-8")

    doc_rows = parse_env_doc(env_md)
    registry = build_env_registry(schema, doc_rows)
    ENV_OUT.write_text(json.dumps(registry, indent=1, ensure_ascii=False) + "\n", "utf-8")

    overlaps = build_overlaps(schema, env_md, settings_md)
    OVERLAPS_OUT.write_text(json.dumps(overlaps, indent=1, ensure_ascii=False) + "\n", "utf-8")

    print(f"schema: {len(schema.get('properties', {}))} top-level keys → {SCHEMA_OUT}")
    print(f"env: {len(registry)} variables (schema {sum(1 for v in registry.values() if v['inSchema'])}, "
          f"docs {len(doc_rows)}) → {ENV_OUT}")
    print(f"overlaps: {len(overlaps)} settings / {sum(len(v) for v in overlaps.values())} pairs → {OVERLAPS_OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
