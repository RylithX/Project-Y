"""
Registry for media source plugins, STT providers, and event detectors.
"""
import re
from typing import List, Tuple, Dict, Type, Optional, Callable
from .base_source import BaseMediaSource

class SourcePluginRegistry:
    _sources: List[Tuple[int, BaseMediaSource]] = []

    @classmethod
    def register(cls, priority: int = 50):
        def decorator(source_cls):
            instance = source_cls()
            cls._sources.append((priority, instance))
            cls._sources.sort(key=lambda x: x[0], reverse=True)
            return source_cls
        return decorator

    @classmethod
    def find_source(cls, url_or_path: str) -> Optional[BaseMediaSource]:
        for _, src in cls._sources:
            try:
                if src.match(url_or_path):
                    return src
            except Exception:
                continue
        return None

    @classmethod
    def get_all_sources(cls) -> List[BaseMediaSource]:
        return [src for _, src in cls._sources]

class STTProviderRegistry:
    _providers: Dict[str, Callable] = {}

    @classmethod
    def register(cls, name: str):
        def decorator(func):
            cls._providers[name.lower()] = func
            return func
        return decorator

    @classmethod
    def get(cls, name: str) -> Optional[Callable]:
        return cls._providers.get(name.lower())

def register_source(priority: int = 50):
    return SourcePluginRegistry.register(priority=priority)

def register_stt_provider(name: str):
    return STTProviderRegistry.register(name)
