"""overlaps.json 생성: 설정 키 ↔ env 변수 겹침(문서 문장에서 추출)."""
from __future__ import annotations

import re

from .markdown import ROW, clean_markdown
from .pkg import ENV_KEY, Precedence

_ENV_NAME = re.compile(r"\b([A-Z][A-Z0-9_]{6,})\b")


def _sentences_about(text: str, needle: str) -> str:
    """text 에서 needle(대소문자 무시)이 들어간 문장만 이어 붙인다."""
    parts = re.split(r"(?<=[.!?])\s+", text)
    return " ".join(s for s in parts if needle.lower() in s.lower()).strip()


def _precedence(key: str, env: str, env_row: str, setting_body: str, env_first: set[str]) -> Precedence:
    """문서 문장에 정확히 앵커된 규칙으로만 판정. 확신이 없으면 RELATED."""
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
        return Precedence.ENV
    if any(re.search(p, text, re.I) for p in setting_wins):
        return Precedence.SETTING
    return Precedence.RELATED


def build_overlaps(schema: dict, env_md: str, settings_md: str) -> dict[str, list[dict]]:
    """설정 키 → [{env, precedence: env|setting|related, note}]. 세 출처의 합집합.

    1) env 문서 행의 settings-reference#anchor 링크
    2) 스키마 설정 description 이 언급하는 env 이름
    3) settings-reference 문서에서 각 설정 절이 언급하는 env 이름
    """
    keys = {k.lower(): k for k in schema.get("properties", {}) if k != ENV_KEY}
    envs = set(schema.get("properties", {}).get(ENV_KEY, {}).get("properties", {}))
    env_rows: dict[str, str] = {}
    for line in env_md.splitlines():
        m = ROW.match(line)
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
        if key == ENV_KEY:
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
            entries.append({"env": env, "precedence": prec.value, "note": note[:400]})
        out[key] = entries
    return out
