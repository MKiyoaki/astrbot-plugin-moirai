"""Shared caching utilities.

_LRUCache       — generic bounded LRU dict (text→embedding, identity lookup, …)
TTLCache        — time-to-live cache for short-lived DB query results.
BoundedKeysMixin — mixin for classes that maintain several parallel dicts keyed
                   by the same token (uid, session_id, …).  Tracks LRU order and
                   fires _on_evict(key) when the key set grows beyond maxsize.
"""
from __future__ import annotations

import time as _time
from collections import OrderedDict
from typing import Generic, TypeVar

_V = TypeVar("_V")


class _LRUCache(Generic[_V]):
    """Bounded LRU cache.  O(1) get/put via OrderedDict."""

    def __init__(self, maxsize: int) -> None:
        self._maxsize = maxsize
        self._cache: OrderedDict[object, _V] = OrderedDict()

    def get(self, key: object) -> _V | None:
        if key not in self._cache:
            return None
        self._cache.move_to_end(key)
        return self._cache[key]  # type: ignore[return-value]

    def put(self, key: object, value: _V) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            if len(self._cache) >= self._maxsize:
                self._cache.popitem(last=False)
        self._cache[key] = value

    def __len__(self) -> int:
        return len(self._cache)


class TTLCache(Generic[_V]):
    """Single-slot TTL cache.  Stores one value that expires after *ttl* seconds.

    Typical use: caching an expensive DB call (e.g. list_frequent_tags) that
    produces the same result for all callers within a short window.
    """

    def __init__(self, ttl: float) -> None:
        self._ttl = ttl
        self._value: _V | None = None
        self._expires_at: float = 0.0

    def get(self) -> _V | None:
        if _time.monotonic() < self._expires_at:
            return self._value
        return None

    def put(self, value: _V) -> None:
        self._value = value
        self._expires_at = _time.monotonic() + self._ttl

    def invalidate(self) -> None:
        self._expires_at = 0.0


class BoundedKeysMixin:
    """Mixin that limits the number of unique keys tracked across parallel dicts.

    Subclass contract
    -----------------
    1. Call ``_init_keys(maxsize)`` inside ``__init__``.
    2. Call ``_touch(key)`` whenever a key is first seen or accessed.
    3. Override ``_on_evict(key)`` to clean up all per-key storage.

    Example::

        class MyStore(BoundedKeysMixin):
            def __init__(self, maxsize: int = 500) -> None:
                self._init_keys(maxsize)
                self._data: dict[str, Any] = {}

            def set(self, key: str, value: Any) -> None:
                self._touch(key)
                self._data[key] = value

            def _on_evict(self, key: str) -> None:
                self._data.pop(key, None)
    """

    def _init_keys(self, maxsize: int) -> None:
        self.__maxsize = maxsize
        self.__order: OrderedDict[object, None] = OrderedDict()

    def _touch(self, key: object) -> None:
        """Register or refresh *key*.  Evicts the LRU key when over capacity."""
        if key in self.__order:
            self.__order.move_to_end(key)
        else:
            if len(self.__order) >= self.__maxsize:
                evicted, _ = self.__order.popitem(last=False)
                self._on_evict(evicted)
            self.__order[key] = None

    def _on_evict(self, key: object) -> None:
        """Called with the evicted key.  Override to clean up per-key state."""

    @property
    def _tracked_key_count(self) -> int:
        return len(self.__order)
