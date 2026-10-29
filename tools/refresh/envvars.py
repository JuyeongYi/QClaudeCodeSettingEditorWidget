"""env-vars.json 생성: 스키마 env 속성 + env-vars.md 표 + overrides 의 손으로 추가한 변수."""
from __future__ import annotations

import re

from .markdown import clean_markdown
from .pkg import ENV_KEY


def suggest_values(desc: str) -> list[str]:
    """문서 설명에서 값 힌트를 추론(불리언 성격의 변수)."""
    if re.search(r"\bset to (1|true)\b", desc, re.IGNORECASE):
        if re.search(r"\btrue\b", desc) and not re.search(r"\bset to 1\b", desc, re.IGNORECASE):
            return ["true", "false"]
        return ["1", "0"]
    return []


def build_env_registry(schema: dict, doc_rows: dict[str, str], overrides: dict[str, dict] | None = None) -> dict[str, dict]:
    """{NAME: {description, schemaDescription, values, inSchema, inDocs[, valuesAreHints]}}.

    overrides 는 공식 스키마·문서에 아직 없는 변수(또는 보정)를 필드 단위로 덮어쓴다. values 를 주면 힌트가 아니다.
    """
    env_props = schema.get("properties", {}).get(ENV_KEY, {}).get("properties", {})
    overrides = overrides or {}
    names = sorted(set(env_props) | set(doc_rows) | set(overrides))
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
        ov = overrides.get(name, {})
        entry.update({k: v for k, v in ov.items() if not k.startswith("_")})
        if not entry["values"]:
            entry["values"] = suggest_values(entry["description"])
            entry["valuesAreHints"] = bool(entry["values"])
        elif "values" in ov:
            entry.setdefault("valuesAreHints", False)
        out[name] = entry
    return out
