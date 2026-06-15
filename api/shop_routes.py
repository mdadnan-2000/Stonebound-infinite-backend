"""
api/shop_routes.py
===================
REST endpoints for the Black Market UI.

SECURITY PRINCIPLE:
The backend is the absolute source of truth for ALL pricing and tier limits.
The frontend never dictates what something costs. Every transaction here:
  1. Looks up the authoritative cost from shop_matrix.py
  2. Verifies the player can afford it
  3. Verifies they haven't exceeded the tier ceiling
  4. Applies the transaction atomically

This prevents any client-side manipulation of item costs or tier bypasses.
"""

from flask import Blueprint, request
from utils.persistence import get_profile, update_profile
from utils.helpers import success, error, require_fields
from core.shop_matrix import (
    full_shop_catalog,
    get_integrity_tier,
    get_velocity_tier,
    get_freeze_upgrade_tier,
    get_spell_purchase_cost,
    get_max_spell_carry,
    INTEGRITY_TIERS,
    VELOCITY_TIERS,
    FREEZE_SPELL_UPGRADE_TIERS,
)

shop_bp = Blueprint("shop", __name__, url_prefix="/shop")


@shop_bp.route("/catalog", methods=["GET"])
def catalog():
    """
    GET /shop/catalog
    Returns the complete Black Market item catalog.

    Called: When the player enters the Black Market UI.
    The frontend renders all upgrade rows and costs from this response —
    NOTHING is hardcoded on the client.

    No authentication required (catalog is public info).
    """
    return success(full_shop_catalog())


@shop_bp.route("/upgrade/integrity", methods=["POST"])
def upgrade_integrity():
    """
    POST /shop/upgrade/integrity
    Upgrades the player's Max Integrity (Core Capacity) by one tier.

    Funded with: GOLD

    Body:
      { "player_id": "uuid-string" }

    Validation:
      - Player must exist
      - Player must not already be at max tier
      - Player must have enough Gold for the NEXT tier's cost

    Returns updated profile snapshot.
    """
    body = request.get_json(silent=True) or {}
    missing = require_fields(body, "player_id")
    if missing:
        return error("missing_field", f"Required field missing: {missing}")

    player_id = body["player_id"]
    profile = get_profile(player_id)
    if not profile:
        return error("player_not_found", f"No player with ID: {player_id}", 404)

    current_tier = profile.get("integrity_level", 0)
    next_tier = current_tier + 1
    max_tier = INTEGRITY_TIERS[-1]["tier"]

    if current_tier >= max_tier:
        return error("max_tier_reached", "Core Capacity is already at maximum tier.")

    next_cfg = get_integrity_tier(next_tier)
    if not next_cfg:
        return error("invalid_tier", f"Tier {next_tier} configuration not found.")

    cost = next_cfg["cost_gold"]
    current_gold = profile.get("gold", 0)

    if current_gold < cost:
        return error(
            "insufficient_gold",
            f"Not enough Gold. Required: {cost}, Have: {current_gold}",
            402
        )

    new_gold = current_gold - cost
    updated = update_profile(player_id, {
        "integrity_level": next_tier,
        "gold": new_gold,
    })

    return success({
        "upgraded_to_tier": next_tier,
        "tier_details": next_cfg,
        "gold_spent": cost,
        "gold_remaining": new_gold,
        "profile_snapshot": _mini_profile(updated),
    })


@shop_bp.route("/upgrade/velocity", methods=["POST"])
def upgrade_velocity():
    """
    POST /shop/upgrade/velocity
    Upgrades the player's Kinetic Thrusters (Velocity) by one tier.

    Funded with: GOLD

    Body:
      { "player_id": "uuid-string" }
    """
    body = request.get_json(silent=True) or {}
    missing = require_fields(body, "player_id")
    if missing:
        return error("missing_field", f"Required field missing: {missing}")

    player_id = body["player_id"]
    profile = get_profile(player_id)
    if not profile:
        return error("player_not_found", f"No player with ID: {player_id}", 404)

    current_tier = profile.get("velocity_level", 0)
    next_tier = current_tier + 1
    max_tier = VELOCITY_TIERS[-1]["tier"]

    if current_tier >= max_tier:
        return error("max_tier_reached", "Kinetic Thrusters are already at maximum tier.")

    next_cfg = get_velocity_tier(next_tier)
    if not next_cfg:
        return error("invalid_tier", f"Tier {next_tier} configuration not found.")

    cost = next_cfg["cost_gold"]
    current_gold = profile.get("gold", 0)

    if current_gold < cost:
        return error(
            "insufficient_gold",
            f"Not enough Gold. Required: {cost}, Have: {current_gold}",
            402
        )

    new_gold = current_gold - cost
    updated = update_profile(player_id, {
        "velocity_level": next_tier,
        "gold": new_gold,
    })

    return success({
        "upgraded_to_tier": next_tier,
        "tier_details": next_cfg,
        "gold_spent": cost,
        "gold_remaining": new_gold,
        "profile_snapshot": _mini_profile(updated),
    })


@shop_bp.route("/upgrade/freeze_spell", methods=["POST"])
def upgrade_freeze_spell():
    """
    POST /shop/upgrade/freeze_spell
    Upgrades the Freezing Spell's mechanics by one tier.

    Funded with: DIAMONDS

    Upgrading increases freeze duration and reduces inventory weight,
    allowing the player to carry more spells simultaneously.

    Body:
      { "player_id": "uuid-string" }
    """
    body = request.get_json(silent=True) or {}
    missing = require_fields(body, "player_id")
    if missing:
        return error("missing_field", f"Required field missing: {missing}")

    player_id = body["player_id"]
    profile = get_profile(player_id)
    if not profile:
        return error("player_not_found", f"No player with ID: {player_id}", 404)

    current_tier = profile.get("freeze_spell_level", 1)
    next_tier = current_tier + 1
    max_tier = FREEZE_SPELL_UPGRADE_TIERS[-1]["tier"]

    if current_tier >= max_tier:
        return error("max_tier_reached", "Freezing Spell is already at maximum tier.")

    next_cfg = get_freeze_upgrade_tier(next_tier)
    if not next_cfg:
        return error("invalid_tier", f"Freeze spell tier {next_tier} not found.")

    cost = next_cfg["cost_diamonds"]
    current_diamonds = profile.get("diamonds", 0)

    if current_diamonds < cost:
        return error(
            "insufficient_diamonds",
            f"Not enough Diamonds. Required: {cost}, Have: {current_diamonds}",
            402
        )

    new_diamonds = current_diamonds - cost

    # When upgrading, recompute max carry capacity and trim held spells if needed.
    # WHY TRIM: If old tier allowed 4 spells but new tier allows 5, no trim needed.
    # But if somehow going backwards (shouldn't happen), we cap it. Safe to always check.
    new_max_carry = get_max_spell_carry(next_tier)
    current_held = profile.get("freeze_spells_held", 0)
    new_held = min(current_held, new_max_carry)  # Never trim up (only protect against edge cases)

    updated = update_profile(player_id, {
        "freeze_spell_level": next_tier,
        "diamonds": new_diamonds,
        "freeze_spells_held": new_held,
    })

    return success({
        "upgraded_to_tier": next_tier,
        "tier_details": next_cfg,
        "diamonds_spent": cost,
        "diamonds_remaining": new_diamonds,
        "max_spells_carriable": new_max_carry,
        "spells_held": new_held,
        "profile_snapshot": _mini_profile(updated),
    })


@shop_bp.route("/buy/freeze_spell", methods=["POST"])
def buy_freeze_spell():
    """
    POST /shop/buy/freeze_spell
    Purchases one consumable Freezing Spell unit using Gold.

    The cost is determined by the player's CURRENT spell tier level —
    better spell = higher unit cost (you're buying a refined spell, not a shard).

    Body:
      { "player_id": "uuid-string" }

    Validation:
      - Player must have enough Gold
      - Player must not be at their carry capacity (based on spell tier weight)
    """
    body = request.get_json(silent=True) or {}
    missing = require_fields(body, "player_id")
    if missing:
        return error("missing_field", f"Required field missing: {missing}")

    player_id = body["player_id"]
    profile = get_profile(player_id)
    if not profile:
        return error("player_not_found", f"No player with ID: {player_id}", 404)

    spell_tier = profile.get("freeze_spell_level", 1)
    max_carry = get_max_spell_carry(spell_tier)
    current_held = profile.get("freeze_spells_held", 0)

    # ── CARRY CAPACITY CHECK ──────────────────────────────────────────────
    if current_held >= max_carry:
        return error(
            "carry_limit_reached",
            f"Spell inventory is full. Current tier allows {max_carry} spell(s). "
            f"Upgrade your Freezing Spell level to carry more.",
            409
        )

    # ── COST CHECK ────────────────────────────────────────────────────────
    cost = get_spell_purchase_cost(spell_tier)
    if cost is None:
        return error("invalid_spell_tier", f"No purchase cost defined for spell tier {spell_tier}.")

    current_gold = profile.get("gold", 0)
    if current_gold < cost:
        return error(
            "insufficient_gold",
            f"Not enough Gold. Required: {cost}, Have: {current_gold}",
            402
        )

    new_gold = current_gold - cost
    new_held = current_held + 1

    updated = update_profile(player_id, {
        "gold": new_gold,
        "freeze_spells_held": new_held,
    })

    return success({
        "spells_held": new_held,
        "max_spells_carriable": max_carry,
        "gold_spent": cost,
        "gold_remaining": new_gold,
        "spell_tier": spell_tier,
        "profile_snapshot": _mini_profile(updated),
    })


@shop_bp.route("/player_state/<player_id>", methods=["GET"])
def player_shop_state(player_id: str):
    """
    GET /shop/player_state/<player_id>
    Returns the player's current upgrade levels and currency balances
    alongside the full catalog, pre-flagged to show what they can/can't afford.

    Called: When entering the Black Market UI — provides everything needed
    to render the shop in a single request without client-side price math.
    """
    profile = get_profile(player_id)
    if not profile:
        return error("player_not_found", f"No player with ID: {player_id}", 404)

    catalog = full_shop_catalog()
    gold = profile.get("gold", 0)
    diamonds = profile.get("diamonds", 0)
    spell_tier = profile.get("freeze_spell_level", 1)

    # Annotate each upgrade tier with affordability flags for the frontend
    def annotate_gold(tiers, current_tier_key):
        current = profile.get(current_tier_key, 0)
        return [
            {**t, "is_current": t["tier"] == current,
             "is_affordable": gold >= t.get("cost_gold", 0),
             "is_unlocked": t["tier"] <= current}
            for t in tiers
        ]

    def annotate_diamond(tiers, current_tier_key):
        current = profile.get(current_tier_key, 1)
        return [
            {**t, "is_current": t["tier"] == current,
             "is_affordable": diamonds >= t.get("cost_diamonds", 0),
             "is_unlocked": t["tier"] <= current}
            for t in tiers
        ]

    return success({
        "player_currencies": {"gold": gold, "diamonds": diamonds},
        "current_upgrade_levels": {
            "integrity_level": profile.get("integrity_level", 0),
            "velocity_level": profile.get("velocity_level", 0),
            "freeze_spell_level": spell_tier,
        },
        "freeze_spells_held": profile.get("freeze_spells_held", 0),
        "max_spells_carriable": get_max_spell_carry(spell_tier),
        "spell_purchase_cost_gold": get_spell_purchase_cost(spell_tier),
        "catalog": {
            "integrity_upgrades": annotate_gold(catalog["integrity_upgrades"], "integrity_level"),
            "velocity_upgrades": annotate_gold(catalog["velocity_upgrades"], "velocity_level"),
            "freeze_spell_upgrades": annotate_diamond(catalog["freeze_spell_upgrades"], "freeze_spell_level"),
        },
    })


# ──────────────────────────────────────────────
# PRIVATE HELPERS
# ──────────────────────────────────────────────

def _mini_profile(profile: dict) -> dict:
    """
    Returns a lightweight profile snapshot for shop transaction responses.
    Frontend uses this to update UI counters immediately after a purchase
    without needing a full GET /player/<id> call.
    """
    return {
        "gold": profile.get("gold", 0),
        "diamonds": profile.get("diamonds", 0),
        "integrity_level": profile.get("integrity_level", 0),
        "velocity_level": profile.get("velocity_level", 0),
        "freeze_spell_level": profile.get("freeze_spell_level", 1),
        "freeze_spells_held": profile.get("freeze_spells_held", 0),
    }
