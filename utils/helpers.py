"""
utils/helpers.py
=================
Shared utilities: response formatting, input validation, and error helpers.

WHY CENTRALIZE RESPONSES:
Every API endpoint returns the same envelope structure. Centralizing this
prevents drift (some endpoints returning {"status": "ok"}, others returning
{"success": true}) which would frustrate frontend developers.

ENVELOPE FORMAT:
{
  "ok": true | false,
  "data": { ... } | null,
  "error": null | { "code": str, "message": str }
}
"""

from flask import jsonify
from typing import Any, Optional


# ──────────────────────────────────────────────
# RESPONSE BUILDERS
# ──────────────────────────────────────────────

def success(data: Any = None, status_code: int = 200):
    """
    Returns a successful JSON response wrapped in the standard envelope.
    `data` can be any JSON-serializable object.
    """
    return jsonify({
        "ok": True,
        "data": data,
        "error": None,
    }), status_code


def error(code: str, message: str, status_code: int = 400):
    """
    Returns an error JSON response.

    `code` is a machine-readable snake_case string for the frontend to
    switch on (e.g., "insufficient_gold", "max_tier_reached").
    `message` is a human-readable explanation.
    """
    return jsonify({
        "ok": False,
        "data": None,
        "error": {
            "code": code,
            "message": message,
        },
    }), status_code


# ──────────────────────────────────────────────
# INPUT VALIDATION HELPERS
# ──────────────────────────────────────────────

def require_fields(body: dict, *fields: str) -> Optional[str]:
    """
    Checks that all required fields are present in the request body.
    Returns the name of the first missing field, or None if all present.

    Usage:
        missing = require_fields(body, "player_id", "elapsed_seconds")
        if missing:
            return error("missing_field", f"Required field: {missing}")
    """
    for field in fields:
        if field not in body or body[field] is None:
            return field
    return None


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamps a value between min and max (inclusive)."""
    return max(min_val, min(max_val, value))


def safe_int(value: Any, default: int = 0) -> int:
    """Safely converts a value to int, returning default on failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    """Safely converts a value to float, returning default on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
