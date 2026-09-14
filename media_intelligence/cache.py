"""
Persistent and in-memory cache for media intelligence results.
"""
import os
import json
import time
import hashlib
from typing import Optional, Dict, Any
from .config import CACHE_DIR, CACHE_EXPIRY_SECONDS

class MediaCache:
    _memory_cache: Dict[str, Dict[str, Any]] = {}
    _max_memory_items: int = 250

    def __init__(self, cache_dir: str = CACHE_DIR, expiry_sec: int = CACHE_EXPIRY_SECONDS):
        self.cache_dir = cache_dir
        self.expiry_sec = expiry_sec
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
        except Exception:
            pass

    def _hash_key(self, key: str) -> str:
        return hashlib.sha256(key.strip().encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        h = self._hash_key(key)
        now = time.time()

        # 1. Check in-memory LRU cache
        if h in self._memory_cache:
            entry = self._memory_cache[h]
            if now - entry.get("_cached_at", 0) < self.expiry_sec:
                return entry.get("data")
            else:
                del self._memory_cache[h]

        # 2. Check disk cache
        path = os.path.join(self.cache_dir, f"{h}.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    entry = json.load(f)
                if now - entry.get("_cached_at", 0) < self.expiry_sec:
                    self._memory_cache[h] = entry
                    return entry.get("data")
                else:
                    try: os.remove(path)
                    except: pass
            except Exception:
                pass
        return None

    def set(self, key: str, data: Dict[str, Any]):
        h = self._hash_key(key)
        now = time.time()
        entry = {
            "_cached_at": now,
            "key": key[:200],
            "data": data
        }

        # Memory store
        if len(self._memory_cache) >= self._max_memory_items:
            # Pop oldest
            oldest_k = next(iter(self._memory_cache))
            del self._memory_cache[oldest_k]
        self._memory_cache[h] = entry

        # Disk store
        path = os.path.join(self.cache_dir, f"{h}.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(entry, f, ensure_ascii=False)
        except Exception:
            pass

    def clear(self):
        self._memory_cache.clear()
        if os.path.exists(self.cache_dir):
            for f in os.listdir(self.cache_dir):
                if f.endswith(".json"):
                    try: os.remove(os.path.join(self.cache_dir, f))
                    except: pass
