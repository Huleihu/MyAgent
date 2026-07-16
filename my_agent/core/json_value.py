"""
本文件负责校验跨 Checkpoint Store 保持类型稳定的 JSON 原生值。
本文件不负责序列化、持久化或业务模型转换。
"""

from __future__ import annotations

from math import isfinite
from typing import Any


def validate_json_native(value: Any) -> None:
    """拒绝 JSON 编码时会发生隐式类型转换或无法编码的值。"""
    _validate_json_native(value, active_container_ids=set())


def _validate_json_native(
    value: Any,
    active_container_ids: set[int],
) -> None:
    """递归校验 JSON 原生类型，并拒绝循环容器。"""
    value_type = type(value)
    if value is None or value_type in {str, bool, int}:
        return
    if value_type is float:
        if not isfinite(value):
            raise ValueError("JSON number must be finite")
        return
    if value_type is list:
        _validate_container(value, active_container_ids)
        return
    if value_type is dict:
        if not all(type(key) is str for key in value):
            raise ValueError("JSON object keys must be strings")
        _validate_container(list(value.values()), active_container_ids, value)
        return
    raise ValueError("value must contain only JSON-native types")


def _validate_container(
    values: list[Any],
    active_container_ids: set[int],
    container: Any | None = None,
) -> None:
    """校验容器子项，并只把当前递归路径用于循环检测。"""
    actual_container = values if container is None else container
    container_id = id(actual_container)
    if container_id in active_container_ids:
        raise ValueError("JSON value must not contain circular references")
    active_container_ids.add(container_id)
    try:
        for item in values:
            _validate_json_native(item, active_container_ids)
    finally:
        active_container_ids.remove(container_id)
