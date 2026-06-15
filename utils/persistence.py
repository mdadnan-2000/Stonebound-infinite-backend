"""
utils/persistence.py
=====================
JSON file-based persistence layer for player profiles.

WHY A PLAIN JSON FILE (not SQLite/Postgres):
Per spec requirements — simplicity, portability, zero external dependencies.
The file is treated as a single key-value store: { player_id: profile_object }.

THREAD SAFETY NOTE:
Flask's development server is single-threaded; this is safe.
For production, wrap read/write operations in a threading.Lock.
File I/O is abstracted here so swapping to a real DB later requires
changing only this module.

PROFILE SCHEMA:
{
  "player_id": str,
  "name": str,
  "avatar_frame_id": int,
  "total_exp": int,
  "gold": int,
  "diamonds": int,
  "integrity_level": int,       // Index into INTEGRITY_TIERS
  "velocity_level": int,         // Index into VELOCITY_TIERS
  "freeze_spell_level": int,     // Index into FREEZE_SPELL_UPGRADE_TIERS (1-based)
  "freeze_spells_held": int,     // Current consumable spell count
  "exp_history": [int, ...],     // EXP delta per successful run (for line graph)
  "created_at": str,             // ISO 8601 timestamp
  "updated_at": str              // ISO 8601 timestamp
}
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional


# Path to the JSON data file.
# Using an absolute path relative to this file ensures it works regardless
# of where Flask is launched from.
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
PROFILES_FILE = os.path.join(DATA_DIR, "profiles.json")


def _ensure_data_dir() -> None:
    """Creates the data directory if it doesn't exist."""
    os.makedirs(DATA_DIR, exist_ok=True)


def _load_all() -> Dict[str, Any]:
    """
    Loads the entire profiles store from disk.
    Returns an empty dict if the file doesn't exist yet.
    """
    _ensure_data_dir()
    if not os.path.exists(PROFILES_FILE):
        return {}
    with open(PROFILES_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            # Corrupted file — return empty rather than crashing
            return {}


def _save_all(data: Dict[str, Any]) -> None:
    """
    Persists the entire profiles store back to disk atomically.
    WHY ATOMIC (write to temp file then rename):
    If the process crashes mid-write, the original file is not corrupted.
    """
    _ensure_data_dir()
    tmp_path = PROFILES_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, PROFILES_FILE)  # Atomic on POSIX systems


def _now() -> str:
    """Returns current UTC timestamp as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _default_profile(player_id: str, name: str = "Wayfarer") -> Dict[str, Any]:
    """
    Creates a fresh profile with all default starting values.

    Starting state per spec:
    - 0 EXP (Level 1 effectively)
    - 0 Gold, 0 Diamonds
    - Integrity at tier 0 (100% max)
    - Velocity at tier 0 (base speed)
    - Freeze Spell at tier 1 (base spell, max 2 held)
    - 0 consumable spells held
    - Empty EXP history
    """
    return {
        "player_id": player_id,
        "name": name,
        "avatar_frame_id": 1,          # Default avatar frame
        "total_exp": 0,
        "gold": 500,                   # Starter gold so new players can visit the shop
        "diamonds": 5,                 # Starter diamonds
        "integrity_level": 0,          # Tier index in INTEGRITY_TIERS
        "velocity_level": 0,           # Tier index in VELOCITY_TIERS
        "freeze_spell_level": 1,       # Tier index in FREEZE_SPELL_UPGRADE_TIERS (1-based)
        "freeze_spells_held": 0,       # Consumable count
        "exp_history": [],             # Filled by complete_level endpoint
        "created_at": _now(),
        "updated_at": _now(),
    }


# ──────────────────────────────────────────────
# PUBLIC API
# ──────────────────────────────────────────────

def create_profile(name: str = "Wayfarer") -> Dict[str, Any]:
    """
    Creates a new player profile with a generated UUID and persists it.
    Returns the newly created profile.
    """
    player_id = str(uuid.uuid4())
    profiles = _load_all()
    profile = _default_profile(player_id, name)
    profiles[player_id] = profile
    _save_all(profiles)
    return profile


def get_profile(player_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetches a player profile by ID.
    Returns None if the player doesn't exist (caller must handle 404).
    """
    profiles = _load_all()
    return profiles.get(player_id, None)


def update_profile(player_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Applies a partial update dict to a player profile and saves.

    WHY PARTIAL UPDATE (not full replace):
    The frontend only sends the fields it changed (name, avatar, currency, etc).
    A full replace would require the client to always send the entire profile,
    creating race-condition and data-loss risks.

    Returns the updated profile, or None if player not found.
    """
    profiles = _load_all()
    if player_id not in profiles:
        return None
    profiles[player_id].update(updates)
    profiles[player_id]["updated_at"] = _now()
    _save_all(profiles)
    return profiles[player_id]


def append_exp_history(player_id: str, exp_delta: int) -> Optional[Dict[str, Any]]:
    """
    Appends an EXP delta to the player's exp_history array.

    WHY A SEPARATE FUNCTION (not just update_profile):
    This operation must be append-only — never truncating or overwriting.
    Keeping it isolated prevents any accidental full-array replacement
    from a careless update_profile call with an incomplete history array.

    exp_delta: The EXP earned in this specific run (positive integer).
    """
    profiles = _load_all()
    if player_id not in profiles:
        return None
    profiles[player_id]["exp_history"].append(exp_delta)
    profiles[player_id]["updated_at"] = _now()
    _save_all(profiles)
    return profiles[player_id]


def list_profiles() -> list:
    """
    Returns a list of all player profiles.
    Useful for debugging or a future leaderboard feature.
    """
    profiles = _load_all()
    return list(profiles.values())


def delete_profile(player_id: str) -> bool:
    """
    Deletes a player profile. Returns True if deleted, False if not found.
    """
    profiles = _load_all()
    if player_id not in profiles:
        return False
    del profiles[player_id]
    _save_all(profiles)
    return True
