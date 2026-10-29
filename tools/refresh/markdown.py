"""공식 문서 마크다운 파서: env-vars.md 의 변수 표, settings-reference.md 의 색인표·키별 섹션."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
ROW = re.compile(r"^\| `([^`]+)`\s*\|(.*)\|\s*$")
_INDEX_ROW = re.compile(r"^\| \[`([^`]+)`\]\(#[^)]*\) \| (.*?) \| (.*?) \| (.*?) \|\s*$", re.M)
_SECTION = re.compile(r"^### `([^`]+)`\s*$", re.M)
_NEXT_HEADING = re.compile(r"^#{2,3} ", re.M)
_VER = r"v(\d+\.\d+\.\d+)"


def clean_markdown(text: str) -> str:
    text = _LINK.sub(r"\1", text)
    text = text.replace("`", "").replace("**", "")
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
        m = ROW.match(line)
        if m:
            rows[m.group(1).strip()] = clean_markdown(m.group(2))
    return rows


@dataclass
class DocEntry:
    """settings-reference.md 의 키(또는 중첩 경로) 하나."""

    path: str
    scope_text: str = ""        # 색인표 Scope 열 또는 섹션의 **Scope** 첫 라벨 ("User or managed" …)
    topic: str = ""
    summary: str = ""           # 색인표 설명(정리된 텍스트)
    description: str = ""       # 섹션 첫 문단(정리된 텍스트)
    type_text: str = ""         # **Type** 줄(원문 마크다운)
    type_bullets: list[str] = field(default_factory=list)  # **Type** 아래 하위 불릿(원문)
    default_text: str = ""      # **Default** 줄(원문)
    since: str | None = None    # "Requires Claude Code vX or later"
    deprecated: bool = False
    deprecated_since: str | None = None
    replaced_by: str | None = None
    removed: str | None = None


def _bullet(body: str, name: str) -> tuple[str, list[str]]:
    """'* **Name**: text' 줄과 그 아래 '  * ' 하위 불릿들."""
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if line.startswith(f"* **{name}**:"):
            subs = []
            for nxt in lines[i + 1:]:
                if not nxt.startswith("  "):
                    break
                if nxt.lstrip().startswith("* "):
                    subs.append(nxt.lstrip()[2:])
            return line.split(":", 1)[1].strip(), subs
    return "", []


def _first_paragraph(body: str) -> str:
    """섹션 첫 문단. 뒤따르는 목록·인용을 가리키며 ':' 로 끝나는 마지막 문장은 뗀다."""
    for para in re.split(r"\n\s*\n", body):
        p = para.strip()
        if p and not p.startswith((">", "* ", "|", "```", "#", "<")):
            text = clean_markdown(p)
            sentences = re.split(r"(?<=[.!?])\s+", text)
            if text.endswith(":") and len(sentences) > 1:
                text = " ".join(sentences[:-1])
            return text
    return ""


def _lifecycle(entry: DocEntry, text: str) -> None:
    """경고 박스·색인 설명의 Deprecated / Removed 문구를 entry 에 반영."""
    if m := re.search(rf"Removed in {_VER}", text):
        entry.removed = entry.removed or m.group(1)
    if re.search(r"\bDeprecated\b", text):
        entry.deprecated = True
        if m := re.search(rf"Deprecated since {_VER}", text):
            entry.deprecated_since = entry.deprecated_since or m.group(1)
        m = (re.search(r"`([\w.]+)`(?:\]\([^)]*\))?(?: object)? replaced it", text)
             or re.search(r"replaced by \[?`([\w.]+)`", text)
             or re.search(r"Deprecated; use `([\w.]+)`", text))
        if m:
            entry.replaced_by = entry.replaced_by or m.group(1)


def parse_settings_reference(markdown: str) -> dict[str, DocEntry]:
    """색인표 행과 '### `key`' 섹션을 합쳐 경로 → DocEntry. 색인표 순서를 따른다."""
    entries: dict[str, DocEntry] = {}
    for m in _INDEX_ROW.finditer(markdown):
        path, summary, topic, scope = m.group(1), m.group(2), m.group(3), m.group(4)
        e = entries.setdefault(path, DocEntry(path))
        e.summary, e.topic, e.scope_text = clean_markdown(summary), clean_markdown(topic), clean_markdown(scope)
        _lifecycle(e, summary)
        if s := re.search(rf"\bRequires (?:Claude Code )?{_VER} or later", summary):
            e.since = s.group(1)

    starts = list(_SECTION.finditer(markdown))
    for m in starts:
        path = m.group(1)
        rest = markdown[m.end():]
        nxt = _NEXT_HEADING.search(rest)
        body = rest[: nxt.start()] if nxt else rest
        e = entries.setdefault(path, DocEntry(path))
        callout = "\n".join(line[1:] for line in body.splitlines() if line.startswith(">"))
        _lifecycle(e, callout)
        e.description = _first_paragraph(body)
        e.type_text, e.type_bullets = _bullet(body, "Type")
        e.default_text, _ = _bullet(body, "Default")
        scope_line, _ = _bullet(body, "Scope")
        if not e.scope_text and (sm := re.match(r"\[?`([^`]+)`", scope_line)):
            e.scope_text = sm.group(1)
        prose = body.split("* **Scope**", 1)[0]
        if not e.since and (s := re.search(rf"\bRequires Claude Code {_VER} or later", prose)):
            e.since = s.group(1)
    return entries
