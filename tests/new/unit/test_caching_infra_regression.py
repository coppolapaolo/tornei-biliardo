"""Regression infra (review 2026-06-09): caching.

- caching/manager.py:223 — _evict_entries non gestiva HYBRID: nessuna rimozione
  ma evictions++ → L2 (HYBRID, max_size=2000) cresceva illimitata.
- caching/manager.py:463 — il decorator `cached` usava `is not None`: i valori
  None salvati erano indistinguibili da un miss → funzioni che ritornano None
  rieseguite ogni volta.
- classification/gara_classification.py:26 — key_generator="gara" ignorava
  round_number → tutti i round collidono sulla stessa chiave.
"""

from __future__ import annotations

import pytest

from models.base import utc_now
from models.caching.manager import (
    MemoryCacheBackend,
    CacheEntry,
    CacheStrategy,
    cached,
    cache_manager,
    gara_round_cache_key,
    gara_cache_key,
)


def _entry(key, value=1, ttl=None):
    now = utc_now()
    return CacheEntry(
        key=key, value=value, created_at=now, last_accessed=now, ttl_seconds=ttl
    )


@pytest.mark.unit
def test_hybrid_backend_stays_bounded():
    backend = MemoryCacheBackend(max_size=10, strategy=CacheStrategy.HYBRID)
    # Inserisci molto più di max_size: deve restare limitata (prima cresceva).
    for i in range(50):
        backend.set(_entry(f"k{i}"))
    assert len(backend._cache) <= 10
    # evictions deve riflettere rimozioni reali (>0), non incrementi a vuoto.
    assert backend._stats.evictions > 0


@pytest.mark.unit
def test_eviction_counter_not_incremented_when_nothing_removed():
    # Backend vuoto: _evict_entries non deve incrementare evictions a vuoto.
    backend = MemoryCacheBackend(max_size=5, strategy=CacheStrategy.HYBRID)
    backend._evict_entries()
    assert backend._stats.evictions == 0


@pytest.mark.unit
def test_lru_backend_still_bounded():
    # Sanity: LRU continua a funzionare dopo il refactor di _evict_entries.
    backend = MemoryCacheBackend(max_size=10, strategy=CacheStrategy.LRU)
    for i in range(30):
        backend.set(_entry(f"k{i}"))
    assert len(backend._cache) <= 10


@pytest.mark.unit
def test_cached_serves_stored_none(db_session):
    # Una funzione cache-ata che ritorna None deve essere servita dalla cache
    # alla seconda chiamata, non rieseguita.
    calls = {"n": 0}

    @cached(ttl_seconds=900)
    def returns_none(x):
        calls["n"] += 1
        return None

    assert returns_none(42) is None
    assert returns_none(42) is None
    assert calls["n"] == 1  # seconda chiamata servita dalla cache


@pytest.mark.unit
def test_gara_round_key_distinguishes_rounds():
    k1 = gara_round_cache_key(5, 1)
    k2 = gara_round_cache_key(5, 2)
    assert k1 != k2
    assert k1 == "gara:5:round:1"
    # Anche via kwargs.
    assert gara_round_cache_key(gara_id=5, round_number=3) == "gara:5:round:3"
    # Il vecchio generator "gara" collassava i round sulla stessa chiave.
    assert gara_cache_key(5, 1) == gara_cache_key(5, 2)


@pytest.mark.unit
def test_gara_round_generator_registered():
    assert "gara_round" in cache_manager._key_generators
