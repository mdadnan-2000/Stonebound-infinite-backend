"""
core/shop_matrix.py
====================
The "Black Market Matrix" — the backend's authoritative shop configuration.

WHY BACKEND-AUTHORITATIVE:
The frontend NEVER defines item costs. All pricing, tier limits, and
upgrade effects live here. This prevents client-side manipulation
(editing localStorage/memory to get free upgrades).

When the player opens the Black Market, the frontend fetches this config
and renders it. When the player buys/upgrades, the backend re-validates
against this config before processing the transaction.

STRUCTURE:
Each upgradeable item has:
  - A list of TIERS (indexed from 0 = starting state, 1 = first upgrade, etc.)
  - Each tier specifies the cost to REACH that tier, the currency type, and
    the mechanical effect that becomes active at that tier.
"""

from typing import Dict, Any


# ──────────────────────────────────────────────────────────────────────────────
# 1. CORE CAPACITY (Max Integrity Upgrades) — Funded with GOLD
# ──────────────────────────────────────────────────────────────────────────────
INTEGRITY_TIERS = [
    # Tier 0: Default starting state (no cost to "purchase")
    {
        "tier": 0,
        "label": "Standard",
        "max_integrity_pct": 100,
        "cost_gold": 0,
        "description": "Default structural integrity. 100% vitality threshold.",
    },
    # Tier 1
    {
        "tier": 1,
        "label": "Reinforced",
        "max_integrity_pct": 125,
        "cost_gold": 300,
        "description": "Reinforced stone plating. +25% vitality. Survive one glancing explosion hit.",
    },
    # Tier 2
    {
        "tier": 2,
        "label": "Fortified",
        "max_integrity_pct": 150,
        "cost_gold": 600,
        "description": "Fortified alloy core. +50% vitality. Absorb medium-range blasts.",
    },
    # Tier 3
    {
        "tier": 3,
        "label": "Reinforced",
        "max_integrity_pct": 175,
        "cost_gold": 800,
        "description": "Ancient rune engraving on hull. +75% vitality. Tank near-direct hits.",
    },
    # Tier 4: Maximum (spec: 200%)
    {
        "tier": 4,
        "label": "Indomitable",
        "max_integrity_pct": 200,
        "cost_gold": 1500,
        "description": "Apex stone infusion. 200% max vitality. Survive a point-blank detonation with minimal life remaining. MAXIMUM TIER.",
    },
]


# ──────────────────────────────────────────────────────────────────────────────
# 2. KINETIC THRUSTERS (Velocity Upgrades) — Funded with GOLD
# ──────────────────────────────────────────────────────────────────────────────
# Spec: 10 upgrade tiers. Each level increases top speed relative to Chasers.
# Chasers are hard-capped at 90% of the player's current velocity tier speed.
VELOCITY_TIERS = [
    {"tier": 0, "label": "Dormant",      "speed_value": 1.00, "cost_gold": 0,    "description": "No thrusters. Standard rolling speed."},
    {"tier": 1, "label": "Awakening",    "speed_value": 1.10, "cost_gold": 150,  "description": "+10% velocity. You begin to outpace newly spawned Chasers."},
    {"tier": 2, "label": "Accelerating", "speed_value": 1.20, "cost_gold": 250,  "description": "+20% velocity. Comfortable lead over single Chasers."},
    {"tier": 3, "label": "Surging",      "speed_value": 1.30, "cost_gold": 400,  "description": "+30% velocity. Reliable escape from 2-Chaser packs."},
    {"tier": 4, "label": "Propelled",    "speed_value": 1.42, "cost_gold": 600,  "description": "+42% velocity. Confidently outrun velocity-waved Chasers."},
    {"tier": 5, "label": "Blazing",      "speed_value": 1.55, "cost_gold": 850,  "description": "+55% velocity. Escape tight dead-end traps with room to spare."},
    {"tier": 6, "label": "Sonic",        "speed_value": 1.70, "cost_gold": 1100, "description": "+70% velocity. Chasers struggle to close the gap in open corridors."},
    {"tier": 7, "label": "Tempest",      "speed_value": 1.88, "cost_gold": 1400, "description": "+88% velocity. You can sprint through trigger zones before bombs detonate."},
    {"tier": 8, "label": "Thundering",   "speed_value": 2.10, "cost_gold": 1800, "description": "+110% velocity. Near-unstoppable in straight corridors."},
    {"tier": 9, "label": "Celestial",    "speed_value": 2.35, "cost_gold": 2300, "description": "+135% velocity. Chasers at 90% cap are visibly slower than you."},
    {"tier": 10, "label": "Apex",        "speed_value": 2.65, "cost_gold": 3000, "description": "+165% velocity. Maximum kinetic output. MAXIMUM TIER."},
]


# ──────────────────────────────────────────────────────────────────────────────
# 3. FREEZING SPELL UPGRADE (Mechanics Upgrade) — Funded with DIAMONDS
# ──────────────────────────────────────────────────────────────────────────────
# Spec: Higher tier = longer freeze duration + smaller inventory footprint
# (allowing more spells to be carried simultaneously).
FREEZE_SPELL_UPGRADE_TIERS = [
    {
        "tier": 1,
        "label": "Glacial Shard",
        "freeze_duration_seconds": 1.5,
        "inventory_weight_pct": 50,  # Takes up 50% of spell slots → max 2 spells
        "cost_diamonds": 0,
        "description": "Basic freeze pulse. 1.5 seconds of stillness. Heavy and bulky — max 2 spells.",
    },
    {
        "tier": 2,
        "label": "Frost Veil",
        "freeze_duration_seconds": 2.0,
        "inventory_weight_pct": 40,  # → max 2 spells (ceiling: floor(100/40) = 2)
        "cost_diamonds": 10,
        "description": "2 seconds of freeze. Slightly more compressed. Max 2 spells.",
    },
    {
        "tier": 3,
        "label": "Cryo Pulse",
        "freeze_duration_seconds": 2.5,
        "inventory_weight_pct": 25,  # → max 4 spells
        "cost_diamonds": 25,
        "description": "2.5 seconds of freeze. Compressed casing — max 4 spells simultaneously.",
    },
    {
        "tier": 4,
        "label": "Arctic Wave",
        "freeze_duration_seconds": 3.5,
        "inventory_weight_pct": 20,  # → max 5 spells
        "cost_diamonds": 50,
        "description": "3.5 seconds of absolute stasis. Compact — max 5 spells.",
    },
    {
        "tier": 5,
        "label": "Void Blizzard",
        "freeze_duration_seconds": 5.0,
        "inventory_weight_pct": 20,  # → max 5 spells
        "cost_diamonds": 100,
        "description": "5 full seconds of total freeze. Maximally compressed — max 5 spells. MAXIMUM TIER.",
    },
]


# ──────────────────────────────────────────────────────────────────────────────
# 4. CONSUMABLE FREEZING SPELL PURCHASE — Funded with GOLD
# ──────────────────────────────────────────────────────────────────────────────
# Players buy individual spell units (not upgrades) using Gold.
# The price scales with current spell tier (better spells cost more).
FREEZE_SPELL_PURCHASE_COST_PER_TIER = {
    1: 75,   # Tier 1 spell: 75 Gold each
    2: 120,  # Tier 2 spell: 120 Gold each
    3: 180,  # Tier 3 spell: 180 Gold each
    4: 250,  # Tier 4 spell: 250 Gold each
    5: 350,  # Tier 5 spell: 350 Gold each
}


# ──────────────────────────────────────────────────────────────────────────────
# HELPER ACCESSORS
# These functions provide safe read access to the matrix data.
# All validation logic in routes will call these to stay DRY.
# ──────────────────────────────────────────────────────────────────────────────

def get_integrity_tier(tier: int) -> Dict[str, Any] | None:
    """Returns the IntegrityTier config for a given tier index, or None."""
    for t in INTEGRITY_TIERS:
        if t["tier"] == tier:
            return t
    return None


def get_velocity_tier(tier: int) -> Dict[str, Any] | None:
    """Returns the VelocityTier config for a given tier index, or None."""
    for t in VELOCITY_TIERS:
        if t["tier"] == tier:
            return t
    return None


def get_freeze_upgrade_tier(tier: int) -> Dict[str, Any] | None:
    """Returns the FreezeSpellUpgradeTier config for a given tier, or None."""
    for t in FREEZE_SPELL_UPGRADE_TIERS:
        if t["tier"] == tier:
            return t
    return None


def get_spell_purchase_cost(spell_tier: int) -> int | None:
    """Returns Gold cost to buy one consumable spell at the given tier level."""
    return FREEZE_SPELL_PURCHASE_COST_PER_TIER.get(spell_tier, None)


def get_max_spell_carry(spell_tier: int) -> int:
    """
    Computes max spells the player can carry based on their spell tier's
    inventory weight percentage.

    WHY FLOOR(100 / weight):
    If each spell takes 25% of inventory, you can hold floor(100/25) = 4 spells.
    This directly implements the spec's "inventory weight loop" mechanic.
    """
    tier_cfg = get_freeze_upgrade_tier(spell_tier)
    if not tier_cfg:
        return 2  # Default to tier-1 limit as fallback
    return max(1, 100 // tier_cfg["inventory_weight_pct"])


def full_shop_catalog() -> Dict[str, Any]:
    """
    Returns the complete Black Market configuration as a single JSON-serializable dict.
    Used by the GET /shop/catalog endpoint so the frontend can render the shop UI
    without any hardcoded pricing on the client side.
    """
    return {
        "integrity_upgrades": INTEGRITY_TIERS,
        "velocity_upgrades": VELOCITY_TIERS,
        "freeze_spell_upgrades": FREEZE_SPELL_UPGRADE_TIERS,
        "freeze_spell_purchase_costs": FREEZE_SPELL_PURCHASE_COST_PER_TIER,
        "max_integrity_tier": INTEGRITY_TIERS[-1]["tier"],
        "max_velocity_tier": VELOCITY_TIERS[-1]["tier"],
        "max_freeze_upgrade_tier": FREEZE_SPELL_UPGRADE_TIERS[-1]["tier"],
    }
