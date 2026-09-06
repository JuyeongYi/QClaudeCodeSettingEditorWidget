"""스키마 노드 → 편집기 팩토리."""
from __future__ import annotations

from ..keys import SettingKey
from ..schema import JsonSchema, resolve_ref, schema_types, variants_of
from .base import BaseEditor
from .containers import (
    AnyOfEditor,
    CheckListEditor,
    DictEditor,
    ListEditor,
    NullableEditor,
    ObjectEditor,
    PropertyRow,
    RawJsonEditor,
    StringListEditor,
)
from .scalars import BoolEditor, ConstEditor, EnumEditor, IntEditor, NullEditor, NumberEditor, StringEditor

MAX_DEPTH = 12
MULTILINE_KEYS = {SettingKey.claudeMd, SettingKey.pluginTrustMessage}

__all__ = [
    "AnyOfEditor", "BaseEditor", "BoolEditor", "CheckListEditor", "ConstEditor", "DictEditor", "EnumEditor",
    "IntEditor", "ListEditor", "NullEditor", "NullableEditor", "NumberEditor", "ObjectEditor", "PropertyRow",
    "RawJsonEditor", "StringEditor", "StringListEditor", "create_editor",
]


def create_editor(schema: JsonSchema, root: JsonSchema, depth: int = 0, key: str | None = None,
                  path: str = "") -> BaseEditor:
    """스키마 노드에 맞는 편집기 생성. 해석 불가한 노드는 RawJsonEditor 로 떨어진다.

    path 는 설명 번역 조회용 경로("permissions.allow", "hooks.PreToolUse[]" 등).
    """
    schema = resolve_ref(schema, root)
    if depth > MAX_DEPTH:
        return RawJsonEditor(schema, root, depth, path=path)

    if "const" in schema:
        return ConstEditor(schema, root, depth, path=path)

    if "anyOf" in schema or "oneOf" in schema:
        variants = variants_of(schema, root)
        if not variants:
            return RawJsonEditor(schema, root, depth, path=path)
        if len(variants) == 1:
            merged = dict(variants[0])
            merged.setdefault("description", schema.get("description", ""))
            return create_editor(merged, root, depth, key, path)
        if all(schema_types(v) == ["string"] for v in variants):
            suggestions: list[str] = []
            for v in variants:
                suggestions.extend(str(e) for e in v.get("enum", []) if str(e) not in suggestions)
            merged = {k: v for k, v in schema.items() if k not in ("anyOf", "oneOf")}
            merged["type"] = "string"
            return StringEditor(merged, root, depth, suggestions=suggestions, path=path)
        return AnyOfEditor(variants, schema, root, depth, path=path)

    types = schema_types(schema)
    if len(types) > 1:
        if "null" in types and len(types) == 2:
            inner = dict(schema)
            inner["type"] = next(t for t in types if t != "null")
            return NullableEditor(inner, schema, root, depth, path=path)
        variants = [dict(schema, type=t) for t in types]
        return AnyOfEditor(variants, schema, root, depth, path=path)

    t = types[0] if types else None
    if t == "string":
        if "enum" in schema:
            return EnumEditor(schema, root, depth, path=path)
        return StringEditor(schema, root, depth, multiline=key in MULTILINE_KEYS, path=path)
    if t == "boolean":
        return BoolEditor(schema, root, depth, path=path)
    if t == "integer":
        return IntEditor(schema, root, depth, path=path)
    if t == "number":
        return NumberEditor(schema, root, depth, path=path)
    if t == "null":
        return NullEditor(schema, root, depth, path=path)
    if t == "array":
        items = resolve_ref(schema.get("items", {}), root) if isinstance(schema.get("items"), dict) else {}
        item_types = schema_types(items)
        if item_types == ["string"] and "enum" in items:
            return CheckListEditor(schema, root, depth, path=path)
        if item_types == ["string"] and "anyOf" not in items and "oneOf" not in items:
            return StringListEditor(schema, root, depth, path=path)
        if not items:
            return RawJsonEditor(schema, root, depth, path=path)
        return ListEditor(schema, root, depth, path=path)
    if t == "object":
        addl = schema.get("additionalProperties")
        if schema.get("properties"):
            return ObjectEditor(schema, root, depth, path=path)
        if isinstance(addl, dict):
            return DictEditor(schema, root, depth, path=path)
        return RawJsonEditor(schema, root, depth, path=path)
    return RawJsonEditor(schema, root, depth, path=path)
