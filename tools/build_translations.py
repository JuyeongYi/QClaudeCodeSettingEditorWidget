"""번역 파일(.ts/.qm) 생성·갱신·컴파일.

소스 문자열 수집
- "qccse"  컨텍스트: 패키지 소스의 tr("...") 호출 + categories.CATEGORY_TITLES 값 + "_name"(언어 표시 이름)
- "schema" 컨텍스트: 스키마의 description 이 있는 모든 노드 경로 + env-vars.json 의 "env.<NAME>"

사용법
  python tools/build_translations.py                  # 기존 locales/qccse_*.ts 를 갱신(en 제외)
  python tools/build_translations.py --lang ja        # 새 언어 파일 생성
  python tools/build_translations.py --import ko schema=ko.descriptions.json qccse=ko_ui.json
                                                       # {source: translation} JSON 을 컨텍스트별로 반영
  python tools/build_translations.py --compile        # pyside6-lrelease 로 .qm 생성
기존 번역은 보존되고, 새 소스는 type="unfinished", 사라진 소스는 type="vanished" 로 표시된다.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "qclaudecodesettingeditorwidget"

sys.path.insert(0, str(ROOT))
from qclaudecodesettingeditorwidget import categories  # noqa: E402
from qclaudecodesettingeditorwidget.constants import (  # noqa: E402
    CONTEXT_SCHEMA,
    CONTEXT_UI,
    ENV_KEY,
    LOCALE_DIR,
    LOCALE_FILE_PREFIX,
    SOURCE_LANG,
)
from qclaudecodesettingeditorwidget.schema import load_env_registry, load_schema, resolve_ref  # noqa: E402

LOCALES = PKG / LOCALE_DIR
_TR_CALL = re.compile(r'\btr\(\s*"((?:[^"\\]|\\.)*)"')


# --------------------------------------------------------------------------- 소스 수집
def collect_ui_sources() -> list[str]:
    found: dict[str, None] = {"_name": None}
    for py in sorted(PKG.rglob("*.py")):
        text = py.read_text("utf-8")
        for m in _TR_CALL.finditer(text):
            found[ast.literal_eval('"' + m.group(1) + '"')] = None
    for title in categories.CATEGORY_TITLES.values():
        found[title] = None
    return list(found)


def collect_schema_paths(schema: dict[str, Any]) -> dict[str, str]:
    """description 이 있는 노드의 경로 → 영어 설명(번역자 참고용 코멘트)."""
    out: dict[str, str] = {}

    def walk(node: Any, path: str, depth: int = 0) -> None:
        node = resolve_ref(node, schema)
        if not isinstance(node, dict) or depth > 14:
            return
        if path and node.get("description") and path not in out:
            out[path] = node["description"]
        for key, child in node.get("properties", {}).items():
            walk(child, f"{path}.{key}" if path else key, depth + 1)
        if isinstance(node.get("items"), dict):
            walk(node["items"], path + "[]", depth + 1)
        if isinstance(node.get("additionalProperties"), dict):
            walk(node["additionalProperties"], f"{path}.*" if path else "*", depth + 1)
        for variant in node.get("anyOf", []) + node.get("oneOf", []):
            walk(variant, path, depth + 1)

    for key, prop in schema.get("properties", {}).items():
        if key == ENV_KEY:
            continue
        walk(prop, key)
    for name, info in load_env_registry(schema=schema).items():
        out[f"env.{name}"] = info.description
    return out


# --------------------------------------------------------------------------- .ts 읽기/쓰기
def read_ts(path: Path) -> dict[str, dict[str, str]]:
    """{context: {source: translation}} (빈 번역은 "")."""
    data: dict[str, dict[str, str]] = {}
    if not path.is_file():
        return data
    root = ET.parse(path).getroot()
    for ctx in root.findall("context"):
        name = (ctx.findtext("name") or "").strip()
        bucket = data.setdefault(name, {})
        for msg in ctx.findall("message"):
            src = msg.findtext("source")
            if src is None:
                continue
            tr_el = msg.find("translation")
            bucket[src] = (tr_el.text or "") if tr_el is not None else ""
    return data


def write_ts(path: Path, lang: str, contexts: dict[str, list[tuple[str, str, str, bool]]]) -> None:
    """contexts: {name: [(source, translation, comment, vanished)]}"""
    root = ET.Element("TS", version="2.1", language=lang)
    for name, messages in contexts.items():
        ctx = ET.SubElement(root, "context")
        ET.SubElement(ctx, "name").text = name
        for source, translation, comment, vanished in messages:
            msg = ET.SubElement(ctx, "message")
            ET.SubElement(msg, "source").text = source
            if comment:
                ET.SubElement(msg, "extracomment").text = comment
            tr_el = ET.SubElement(msg, "translation")
            if vanished:
                tr_el.set("type", "vanished")
            elif not translation:
                tr_el.set("type", "unfinished")
            tr_el.text = translation
    tree = ET.ElementTree(root)
    ET.indent(tree, space="    ")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.write(b'<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE TS>\n')
        tree.write(f, encoding="utf-8", xml_declaration=False)
        f.write(b"\n")


def update_language(lang: str, ui_sources: list[str], schema_paths: dict[str, str],
                    imports: dict[str, dict[str, str]] | None = None, keep_vanished: bool = False) -> Path:
    path = LOCALES / f"{LOCALE_FILE_PREFIX}{lang}.ts"
    existing = read_ts(path)
    imports = imports or {}
    contexts: dict[str, list[tuple[str, str, str, bool]]] = {}

    def build(ctx: str, sources: list[str], comments: dict[str, str]) -> None:
        old = existing.get(ctx, {})
        imp = imports.get(ctx, {})
        rows = []
        for src in sources:
            rows.append((src, imp.get(src) or old.get(src, ""), comments.get(src, ""), False))
        if keep_vanished:
            for src, val in old.items():
                if src not in sources and val:
                    rows.append((src, val, "", True))
        contexts[ctx] = rows

    build(CONTEXT_UI, ui_sources, {})
    build(CONTEXT_SCHEMA, list(schema_paths), schema_paths)
    write_ts(path, lang, contexts)
    return path


def compile_qm(ts_path: Path) -> bool:
    exe = shutil.which("pyside6-lrelease") or shutil.which("lrelease")
    if exe is None:
        try:
            import PySide6

            cand = Path(PySide6.__path__[0]) / ("lrelease.exe" if sys.platform == "win32" else "lrelease")
            exe = str(cand) if cand.exists() else None
        except ImportError:
            exe = None
    if exe is None:
        print("lrelease 를 찾을 수 없어 .qm 컴파일을 건너뜁니다 (.ts 는 런타임에 직접 로드됩니다)")
        return False
    qm = ts_path.with_suffix(".qm")
    subprocess.run([exe, str(ts_path), "-qm", str(qm)], check=True)
    return True


def existing_languages() -> list[str]:
    return sorted(p.stem[len(LOCALE_FILE_PREFIX):] for p in LOCALES.glob(f"{LOCALE_FILE_PREFIX}*.ts"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lang", action="append", default=[], help="갱신/생성할 언어 코드(반복 가능). 기본: 기존 .ts 전부")
    ap.add_argument("--import", dest="imports", nargs="+", metavar="ARG", default=None,
                    help="LANG ctx=file.json ... : {source: translation} JSON 을 해당 컨텍스트로 반영")
    ap.add_argument("--compile", action="store_true", help="pyside6-lrelease 로 .qm 컴파일")
    ap.add_argument("--keep-vanished", action="store_true", help="사라진 소스의 번역을 vanished 로 보존")
    args = ap.parse_args(argv)

    schema = load_schema()
    ui_sources = collect_ui_sources()
    schema_paths = collect_schema_paths(schema)
    print(f"UI sources: {len(ui_sources)}, schema paths: {len(schema_paths)}")

    imports: dict[str, dict[str, dict[str, str]]] = {}
    if args.imports:
        lang, specs = args.imports[0], args.imports[1:]
        for spec in specs:
            ctx, _, file = spec.partition("=")
            data = json.loads(Path(file).read_text("utf-8"))
            imports.setdefault(lang, {})[ctx] = {str(k): str(v) for k, v in data.items()}
        if lang not in args.lang:
            args.lang.append(lang)

    langs = args.lang or existing_languages()
    for lang in langs:
        if lang == SOURCE_LANG:
            continue
        path = update_language(lang, ui_sources, schema_paths, imports.get(lang), args.keep_vanished)
        data = read_ts(path)
        done_ui = sum(1 for v in data.get(CONTEXT_UI, {}).values() if v)
        done_schema = sum(1 for v in data.get(CONTEXT_SCHEMA, {}).values() if v)
        print(f"{path.name}: ui {done_ui}/{len(ui_sources)}, schema {done_schema}/{len(schema_paths)}")
        if args.compile:
            compile_qm(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
