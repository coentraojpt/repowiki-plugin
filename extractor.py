from __future__ import annotations

import ast  # noqa: F401 — used by _extract_python (added in later tasks)
import hashlib
import json
import re  # noqa: F401 — used by _extract_regex (added in later tasks)
from pathlib import Path

_CACHE_VERSION = 1


def _md5(path: Path) -> str:
    try:
        return hashlib.md5(path.read_bytes()[:1_048_576]).hexdigest()[:8]  # cap at 1 MB for performance
    except Exception:
        return "00000000"


def _load_cache(cache_path: Path) -> dict:
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        if data.get("version") == _CACHE_VERSION:
            return data
    except Exception:
        pass
    return {"version": _CACHE_VERSION, "entries": {}}


def _save_cache(cache_path: Path, cache: dict) -> None:
    cache_path.write_text(
        json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8"
    )
