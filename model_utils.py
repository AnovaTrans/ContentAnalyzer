"""Live Claude model discovery for the UI dropdown.

Fetches the account's currently available models so the app never ships a
hardcoded, later-retired model id. Falls back to a small current list if the
Models API can't be reached.
"""
from __future__ import annotations

from typing import List

import anthropic

# Current-generation fallback if the live listing fails (no key / no network).
FALLBACK_MODELS = ["claude-opus-5", "claude-sonnet-4-6", "claude-haiku-4-5"]

# Preference order for the default selection when present in the live list.
_PREFERRED = [
    "claude-sonnet-4-6", "claude-opus-4-6", "claude-opus-5",
    "claude-sonnet-5", "claude-haiku-4-5",
]


def list_model_ids(api_key: str) -> List[str]:
    """Return current model ids (newest first). Empty list on any failure."""
    if not api_key:
        return []
    try:
        client = anthropic.Anthropic(api_key=api_key)
        models = list(client.models.list())
        models.sort(key=lambda m: str(getattr(m, "created_at", "") or ""), reverse=True)
        return [m.id for m in models if getattr(m, "id", None)]
    except Exception:
        return []


def default_model(ids: List[str]) -> str:
    """Pick a sensible default from available ids."""
    for pref in _PREFERRED:
        if pref in ids:
            return pref
    return ids[0] if ids else FALLBACK_MODELS[0]
