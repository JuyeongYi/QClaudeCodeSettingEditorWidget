"""CHANGELOG.md 파서: 버전 블록과 '설정 추가' 줄에서 키가 처음 생긴 버전을 찾는다."""
from __future__ import annotations

import re

_TAG = re.compile(r"^(?:\[[^\]]+\]\s*)+")


def parse_changelog(markdown: str) -> list[tuple[str, list[str]]]:
    """[(버전, 항목 줄들)] — 최신 버전이 먼저. 항목 줄은 '- ' 와 '[VSCode] ' 같은 태그를 뗀 텍스트."""
    out: list[tuple[str, list[str]]] = []
    for block in re.split(r"^## ", markdown, flags=re.M)[1:]:
        head, _, body = block.partition("\n")
        version = head.strip()
        if not re.fullmatch(r"\d+\.\d+\.\d+", version):
            continue
        items = [_TAG.sub("", line[2:].strip()) for line in body.splitlines() if line.startswith("- ")]
        out.append((version, items))
    return out


def latest_version(markdown: str) -> str | None:
    versions = parse_changelog(markdown)
    return versions[0][0] if versions else None


def added_versions(markdown: str, paths: set[str]) -> dict[str, str]:
    """'Added `key` setting …', 'Added a `key` setting …' 처럼 줄 첫머리에서 설정 키를 추가했다고 밝힌 가장 이른 버전.

    키가 줄에 언급만 된 경우(다른 기능 설명)는 제외한다 — 'Added' 바로 뒤 몇 단어 안에 `key` 와
    setting/option 이 함께 나와야 한다.
    """
    found: dict[str, str] = {}
    pattern = re.compile(
        r"^Added (?:(?:a|an|the|new|support for(?: the)?)\s+)*"
        r"((?:`[\w.$]+`(?:,\s*|\s+and\s+|\s+or\s+)?)+)\s*(?:\w+\s+){0,2}?(?:settings?|options?|config(?:uration)? keys?)\b")
    for version, items in reversed(parse_changelog(markdown)):  # 오래된 것부터
        for item in items:
            m = pattern.match(item)
            if not m:
                continue
            for key in re.findall(r"`([\w.$]+)`", m.group(1)):
                if key in paths:
                    found.setdefault(key, version)
    return found
