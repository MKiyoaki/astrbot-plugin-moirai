from __future__ import annotations

from copy import deepcopy
from typing import Any


def flatten_conf_schema(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    flat_schema: dict[str, dict[str, Any]] = {}
    for group_data in raw.values():
        if isinstance(group_data, dict) and group_data.get("type") == "object":
            items = group_data.get("items", {})
            if isinstance(items, dict):
                flat_schema.update(items)
    return flat_schema


def schema_field_groups(raw: dict[str, Any]) -> dict[str, str]:
    groups: dict[str, str] = {}
    for group_key, group_data in raw.items():
        if not isinstance(group_data, dict) or group_data.get("type") != "object":
            continue
        items = group_data.get("items", {})
        if not isinstance(items, dict):
            continue
        for field_key in items:
            groups[field_key] = group_key
    return groups


def flat_config_values(source: Any, flat_schema: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(source, dict):
        return {}

    values: dict[str, Any] = {}
    for key, value in source.items():
        if key in flat_schema:
            values[key] = value
        elif not isinstance(value, dict):
            values[key] = value

    for value in source.values():
        if not isinstance(value, dict):
            continue
        for sub_key, sub_value in value.items():
            if sub_key in flat_schema:
                values[sub_key] = sub_value

    return values


def merge_config_values(
    values: dict[str, Any],
    source: Any,
    flat_schema: dict[str, Any],
) -> None:
    values.update(flat_config_values(source, flat_schema))


def normalize_config_document(
    current: dict[str, Any],
    updates: dict[str, Any],
    raw_schema: dict[str, Any],
) -> dict[str, Any]:
    field_groups = schema_field_groups(raw_schema)
    normalized = deepcopy(current)

    for key, group_key in field_groups.items():
        if key not in normalized:
            continue
        group_value = normalized.setdefault(group_key, {})
        if isinstance(group_value, dict) and key not in group_value:
            group_value[key] = normalized[key]
        del normalized[key]

    for key, value in updates.items():
        group_key = field_groups.get(key)
        if not group_key:
            normalized[key] = value
            continue
        group_value = normalized.setdefault(group_key, {})
        if not isinstance(group_value, dict):
            group_value = {}
            normalized[group_key] = group_value
        group_value[key] = value
        normalized.pop(key, None)

    return normalized


def apply_config_update_to_mapping(
    target: Any,
    updates: dict[str, Any],
    raw_schema: dict[str, Any],
) -> None:
    field_groups = schema_field_groups(raw_schema)

    for key, group_key in field_groups.items():
        try:
            root_value = target[key]
        except Exception:
            continue

        try:
            group_value = target[group_key]
        except Exception:
            group_value = None

        if not isinstance(group_value, dict):
            group_value = {}
            target[group_key] = group_value
        if key not in group_value:
            group_value[key] = root_value
        try:
            del target[key]
        except Exception:
            pass

    for key, value in updates.items():
        group_key = field_groups.get(key)
        if not group_key:
            target[key] = value
            continue

        try:
            group_value = target[group_key]
        except Exception:
            group_value = None

        if not isinstance(group_value, dict):
            group_value = {}
            target[group_key] = group_value

        group_value[key] = value
        try:
            if key in target:
                del target[key]
        except Exception:
            pass
