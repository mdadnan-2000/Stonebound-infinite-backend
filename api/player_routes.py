"""
api/player_routes.py
=====================
REST endpoints for player profile management.

Handles: creation, retrieval, identity updates (name + avatar).
All currency and upgrade mutations happen through dedicated routes
(shop_routes.py, game_routes.py) — never here — to enforce separation
of concerns and maintain an audit trail.
"""

from flask import Blueprint, request
from utils.persistence import create_profile, get_profile, update_profile, list_profiles, delete_profile
from utils.helpers import success, error, require_fields
from core.progression import exp_to_level, exp_for_level

# Blueprint groups all /player routes under a common prefix
player_bp = Blueprint("player", __name__, url_prefix="/player")


@player_bp.route("/create", methods=["POST"])
def create():
    """
    POST /player/create
    Creates a new player profile.

    Body (optional):
      { "name": "Wayfarer" }

    Returns the full new profile object with generated player_id.
    The frontend should persist player_id locally (localStorage or cookie)
    and include it in all subsequent requests.
    """
    body = request.get_json(silent=True) or {}
    name = body.get("name", "Wayfarer")

    if not isinstance(name, str) or len(name.strip()) == 0:
        return error("invalid_name", "Player name must be a non-empty string.")
    if len(name) > 30:
        return error("name_too_long", "Player name must be 30 characters or fewer.")

    profile = create_profile(name.strip())
    return success(_enrich_profile(profile), status_code=201)


@player_bp.route("/<player_id>", methods=["GET"])
def get(player_id: str):
    """
    GET /player/<player_id>
    Fetches a player's full profile.

    Called on app startup to hydrate the Intro UI with:
    - Level, EXP, Gold, Diamonds
    - Upgrade levels (integrity, velocity, freeze spell)
    - exp_history (for the line graph)
    - Identity (name, avatar frame)
    """
    profile = get_profile(player_id)
    if not profile:
        return error("player_not_found", f"No player found with ID: {player_id}", 404)
    return success(_enrich_profile(profile))


@player_bp.route("/<player_id>/identity", methods=["PATCH"])
def update_identity(player_id: str):
    """
    PATCH /player/<player_id>/identity
    Updates the player's display name and/or avatar frame.

    Body:
      { "name": "NewName", "avatar_frame_id": 3 }
    Both fields are optional — only provided fields are updated.

    WHY PATCH (not PUT):
    PUT requires sending the full resource; PATCH sends only changes.
    This is the semantically correct method for partial updates.
    """
    profile = get_profile(player_id)
    if not profile:
        return error("player_not_found", f"No player found with ID: {player_id}", 404)

    body = request.get_json(silent=True) or {}
    updates = {}

    if "name" in body:
        name = body["name"]
        if not isinstance(name, str) or len(name.strip()) == 0:
            return error("invalid_name", "Name must be a non-empty string.")
        if len(name) > 30:
            return error("name_too_long", "Name must be 30 characters or fewer.")
        updates["name"] = name.strip()

    if "avatar_frame_id" in body:
        frame_id = body["avatar_frame_id"]
        if not isinstance(frame_id, int) or frame_id < 1:
            return error("invalid_avatar", "avatar_frame_id must be a positive integer.")
        updates["avatar_frame_id"] = frame_id

    if not updates:
        return error("no_changes", "No valid fields provided to update.")

    updated = update_profile(player_id, updates)
    return success(_enrich_profile(updated))


@player_bp.route("/all", methods=["GET"])
def get_all():
    """
    GET /player/all
    Returns all player profiles. Useful for debugging or future leaderboards.
    """
    profiles = list_profiles()
    return success([_enrich_profile(p) for p in profiles])


@player_bp.route("/<player_id>", methods=["DELETE"])
def delete(player_id: str):
    """
    DELETE /player/<player_id>
    Permanently deletes a player profile.
    """
    deleted = delete_profile(player_id)
    if not deleted:
        return error("player_not_found", f"No player found with ID: {player_id}", 404)
    return success({"deleted": True, "player_id": player_id})


# ──────────────────────────────────────────────
# PRIVATE HELPERS
# ──────────────────────────────────────────────

def _enrich_profile(profile: dict) -> dict:
    """
    Augments the raw stored profile with computed fields that the
    frontend needs but we don't want to re-derive on every read.

    WHY COMPUTE-ON-READ:
    Storing computed fields (like current_level) would create sync issues —
    total_exp changes, but someone forgets to update current_level.
    Computing them from the source of truth (total_exp) on every read
    guarantees consistency.
    """
    total_exp = profile.get("total_exp", 0)
    current_level = exp_to_level(total_exp)
    next_level_exp = exp_for_level(current_level + 1)
    current_level_exp = exp_for_level(current_level)
    exp_in_level = total_exp - current_level_exp
    exp_needed = next_level_exp - current_level_exp

    return {
        **profile,
        # Computed progression fields (not stored — always derived from total_exp)
        "current_level": current_level,
        "exp_in_current_level": exp_in_level,
        "exp_to_next_level": exp_needed,
        "next_level_total_exp": next_level_exp,
    }
