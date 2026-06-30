"""
api/game_routes.py
===================
REST endpoints for core game flow:
  1. Generating a new maze level (called from Loading Screen UI)
  2. Completing a level (Victory or Defeat) — awards EXP and currencies

WHY SEPARATE FROM PLAYER ROUTES:
Game actions mutate multiple profile fields atomically (EXP + gold + history).
Isolating these in game_routes.py makes the transactional logic clear
and prevents accidental partial-updates from generic profile endpoints.

STARS:
On a successful run, the backend calculates stars_earned (1–5) and stores the
BEST star rating ever achieved for each level number under
profile["level_stars"][str(level_number)]. The frontend reads this from the
player profile to display earned stars in the Level Progression Panel.

LEVEL REPLAY ("isReplay" CONTEXT WRAPPER):
Both endpoints below now understand an `is_replay` context, driven by the
optional `replay_level` field on `/generate_level` and the optional
`is_replay` / `replay_level` fields on `/complete_level`. This wrapper is the
ONLY thing that changes behavior — the standard progression code paths are
untouched line-for-line. See `_build_replay_context` and the inline branches
marked "REPLAY" below for the complete set of replay-specific rules:
  - Fixed Environment Complexity (maze params pinned to the original level)
  - The Kamikaze Exception (handled client-side via player_snapshot velocity;
    nothing server-side needs to change since chasers always scale off the
    player's CURRENT velocity_multiplier, replay or not)
  - The Empty Maze Rule (loot counts zeroed before maze generation)
  - High-Water Mark Star Tracking (level_stars never decreases)
  - The Star Bounty Currency Rule (gold only for beating the historic best)
  - Zero EXP Impact (replay runs never grant or deduct EXP — total_exp and
    current_level are completely unaffected by replaying; stars/verdict are
    still computed normally so star-mastery and the bounty still work)
"""

import math
from flask import Blueprint, request
from utils.persistence import get_profile, update_profile, append_exp_history
from utils.helpers import success, error, require_fields, safe_int, safe_float, clamp
from core.progression import generate_level_parameters, exp_to_level
from core.maze_engine import generate_maze
from core.exp_engine import calculate_exp_reward, calculate_star_bounty
from core.shop_matrix import get_freeze_upgrade_tier

game_bp = Blueprint("game", __name__, url_prefix="/game")


@game_bp.route("/generate_level", methods=["POST"])
def generate_level():
    """
    POST /game/generate_level
    Generates a complete maze level for the player.

    Called: When the player clicks "Begin Run" or "Reconstruct Ruin (Retry)",
    OR when they click the "Replay" icon on a previously completed level in
    the Level Progression Panel.

    Body:
      { "player_id": "uuid-string" }

    Optional:
      { "player_id": "...", "seed": 12345 }
      Providing a seed creates a deterministic maze (for retry functionality).

      { "player_id": "...", "replay_level": 2 }
      LEVEL REPLAY: Generates level 2 at ITS ORIGINAL difficulty/parameters,
      regardless of the player's current progression level. Requires the
      player to have already earned at least 1 star on that level
      (i.e. it must exist in their `level_stars` map) and that the level be
      strictly lower than their current progression level — you cannot
      "replay" a level you haven't beaten yet, nor your active level.

    Returns:
      Full maze payload including grid, metadata, spawn, exit, loot, hazards.
      When replaying, `loot` arrays are always empty (Empty Maze Rule) and
      the top-level response includes `is_replay`, `replay_level`, and
      `historic_best_stars` so the frontend can drive Replay Mode UI.

    DESIGN NOTE — WHY THE BACKEND GENERATES THE MAZE:
    Generating server-side prevents clients from pre-mapping the maze before
    the level starts, and ensures all players at the same EXP level
    face comparably difficult layouts.
    """
    body = request.get_json(silent=True) or {}

    missing = require_fields(body, "player_id")
    if missing:
        return error("missing_field", f"Required field missing: {missing}")

    player_id = body["player_id"]
    profile = get_profile(player_id)
    if not profile:
        return error("player_not_found", f"No player with ID: {player_id}", 404)

    total_exp = profile.get("total_exp", 0)
    seed = body.get("seed", None)  # Optional deterministic seed for retry
    replay_level_raw = body.get("replay_level", None)

    is_replay = False
    replay_level = None
    historic_best_stars = None

    if replay_level_raw is not None:
        replay_level = safe_int(replay_level_raw, None)
        if replay_level is None or replay_level < 1:
            return error("invalid_replay_level", "replay_level must be a positive integer.")

        current_level = exp_to_level(total_exp)
        level_stars = profile.get("level_stars", {})
        historic_best_stars = level_stars.get(str(replay_level), 0)

        if replay_level >= current_level:
            return error(
                "replay_not_unlocked",
                "You can only replay levels strictly below your current progression level.",
            )
        if historic_best_stars <= 0:
            return error(
                "replay_not_unlocked",
                "You must complete a level at least once before you can replay it.",
            )

        is_replay = True

    # Generate the level parameters (difficulty, grid size, hazard counts, etc.)
    # REPLAY: pass replay_level through so difficulty is derived from THAT level
    # number, not the player's current EXP — this is the "Fixed Environment
    # Complexity" rule, implemented entirely via the isReplay context wrapper.
    params = generate_level_parameters(total_exp, replay_level=replay_level)

    if is_replay:
        # REPLAY: "Empty Maze" rule — strip all floor loot. We zero the counts
        # here (API layer) rather than touching maze_engine.py or progression.py,
        # so standard progression's loot scaling math is never altered.
        params["loot"] = {
            "gold_count": 0,
            "diamond_count": 0,
            "medicine_count": 0,
            "spell_floor_drops": 0,
        }

    # Generate the actual maze grid and entity positions
    maze_payload = generate_maze(params, seed=seed)

    if is_replay:
        maze_payload["metadata"]["is_replay"] = True
        maze_payload["metadata"]["historic_best_stars"] = historic_best_stars

    # Include the player's current stats so the frontend can initialize
    # the gameplay HUD without a separate API call.
    # REPLAY NOTE — "The Kamikaze Exception": these are always the player's
    # CURRENT upgrade values (never the level's historical ones), which is
    # exactly what makes Chasers scale to 90% of the player's TODAY speed
    # even while the maze itself stays at the easy, original difficulty.
    player_snapshot = {
        "freeze_spells_held": profile.get("freeze_spells_held", 0),
        "freeze_spell_level": profile.get("freeze_spell_level", 1),
        "freeze_duration_seconds": _get_freeze_duration(profile),
        "max_integrity_pct": _get_max_integrity(profile),
        "velocity_multiplier": _get_velocity(profile),
    }

    return success({
        "maze": maze_payload,
        "player_snapshot": player_snapshot,
        # Include seed in response so the frontend can pass it back on retry
        "seed": seed,
        "is_replay": is_replay,
        "replay_level": replay_level,
        "historic_best_stars": historic_best_stars,
    })


@game_bp.route("/complete_level", methods=["POST"])
def complete_level():
    """
    POST /game/complete_level
    Processes the end of a level run (both victory and defeat).

    Called: When the player exits the maze OR their Integrity hits 0%.
    This is the most important transactional endpoint — it atomically:
      1. Calculates EXP earned
      2. Awards (or withholds) EXP
      3. Credits collected currencies (or, on replay, the Star Bounty)
      4. Applies defeat penalty (gold loss) if failed
      5. Appends EXP to history (for the line graph)
      6. Stores the best star rating for the completed level number
         (high-water mark — never decreases)
      7. Saves all changes in a single write

    Body:
    {
      "player_id": "uuid-string",
      "failed": false,                  // true = Integrity hit 0%
      "elapsed_seconds": 180,           // Total run time
      "grid_rows": 25,                  // From the generated maze metadata
      "grid_cols": 25,
      "difficulty": 0.42,              // From the generated maze metadata
      "integrity_lost_pct": 0.30,      // e.g., 0.30 = lost 30% of max health
      "backtrack_steps": 15,           // Steps taken in wrong direction
      "total_steps": 120,              // Total movement steps
      "loot_collected_pct": 0.80,      // Fraction of level loot gathered
      "gold_collected": 85,            // Actual gold picked up this run
      "diamonds_collected": 2,         // Actual diamonds picked up this run
      "is_replay": false,              // OPTIONAL — true if this was a Level Replay run
      "replay_level": 2,               // OPTIONAL — required when is_replay is true
      "spells_remaining": 1            // OPTIONAL — freeze spells held at run end (cast/pickup-adjusted)
    }

    Returns:
      EXP calculation breakdown, updated currency totals, performance verdict,
      stars_earned (1–5, or 0 on defeat), and the data needed to render the
      Game Result UI. On replay runs, also includes `bounty_gold`,
      `beat_record`, and `previous_best_stars`. NOTE: `exp_earned` is always
      0 on replay runs — replaying never grants or deducts EXP.
    """
    body = request.get_json(silent=True) or {}

    required = [
        "player_id", "failed", "elapsed_seconds", "grid_rows", "grid_cols",
        "difficulty", "integrity_lost_pct", "backtrack_steps", "total_steps",
        "loot_collected_pct", "gold_collected", "diamonds_collected"
    ]
    missing = require_fields(body, *required)
    if missing:
        return error("missing_field", f"Required field missing: {missing}")

    player_id = body["player_id"]
    profile = get_profile(player_id)
    if not profile:
        return error("player_not_found", f"No player with ID: {player_id}", 404)

    failed = bool(body["failed"])

    # ── REPLAY CONTEXT ──────────────────────────────────────────────────────
    is_replay = bool(body.get("is_replay", False))
    replay_level = None
    if is_replay:
        replay_level = safe_int(body.get("replay_level"), None)
        if replay_level is None or replay_level < 1:
            return error("missing_field", "replay_level is required when is_replay is true.")

    # ── PERFORMANCE METRICS (sanitized) ──────────────────────────────────
    elapsed = safe_int(body["elapsed_seconds"], 1)
    rows = safe_int(body["grid_rows"], 10)
    cols = safe_int(body["grid_cols"], 10)
    difficulty = clamp(safe_float(body["difficulty"], 0.0), 0.0, 1.0)
    integrity_lost = clamp(safe_float(body["integrity_lost_pct"], 0.0), 0.0, 1.0)
    backtrack = safe_int(body["backtrack_steps"], 0)
    total_steps = safe_int(body["total_steps"], 1)
    loot_pct = clamp(safe_float(body["loot_collected_pct"], 0.0), 0.0, 1.0)
    gold_collected = max(0, safe_int(body["gold_collected"], 0))
    diamonds_collected = max(0, safe_int(body["diamonds_collected"], 0))

    # FREEZE SPELL FIX: the gameplay engine tracks the player's held freeze
    # spell count locally (decremented on cast, incremented on floor pickups)
    # but previously never reported it back, so the persisted
    # `freeze_spells_held` on the profile silently never changed across runs.
    # `spells_remaining` is OPTIONAL so older clients keep working unchanged
    # (the field is simply omitted from the profile update in that case).
    # We clamp it defensively: never negative, and never above what the
    # player's CURRENT freeze spell tier can carry — prevents a tampered
    # client payload from inflating spell inventory beyond its real cap.
    spells_remaining = None
    if "spells_remaining" in body and body["spells_remaining"] is not None:
        from core.shop_matrix import get_max_spell_carry
        raw_spells_remaining = max(0, safe_int(body["spells_remaining"], 0))
        max_carry = get_max_spell_carry(profile.get("freeze_spell_level", 1))
        spells_remaining = min(raw_spells_remaining, max_carry)

    # REPLAY: the Empty Maze rule means there is never anything to collect.
    # We defensively zero these out server-side too, so a tampered client
    # payload can never smuggle in floor-loot gold/diamonds on a replay run.
    if is_replay:
        gold_collected = 0
        diamonds_collected = 0

    # ── EXP CALCULATION ──────────────────────────────────────────────────
    # The same composite formula runs for BOTH standard and replay runs —
    # we need it to derive `verdict` and `stars_earned`, which still drive
    # the Star Bounty logic below. The resulting `exp_earned` value itself
    # is discarded for replay runs (see the `is_replay` check right after
    # this call): Level Replay is a pure mastery/gold loop and must NEVER
    # move the player's total_exp or progression level in either direction.
    exp_result = calculate_exp_reward(
        difficulty=difficulty,
        elapsed_seconds=elapsed,
        rows=rows,
        cols=cols,
        integrity_lost_pct=integrity_lost,
        backtrack_steps=backtrack,
        total_steps=total_steps,
        loot_collected_pct=loot_pct,
        failed=failed,
    )

    stars_earned = exp_result["stars_earned"]  # 0 on defeat, 1–5 on success

    # LEVEL REPLAY: stars/verdict still come from the same composite formula
    # (so star-mastery and bounty eligibility work normally), but EXP itself
    # is intentionally withheld. Replaying is purely a mastery/gold loop —
    # it must never move the player's progression bar in either direction.
    exp_earned = 0 if is_replay else exp_result["exp_earned"]

    # ── CURRENCY DELTA ───────────────────────────────────────────────────
    bonus_gold = 0
    bounty_gold = 0
    beat_record = False
    previous_best_stars = None

    if is_replay:
        # ── REPLAY: Star Bounty Currency Rule ───────────────────────────
        # The ONLY gold a replay run can earn is the bounty for beating the
        # historic best star count. No flawless bonus, no floor-loot gold —
        # those don't exist in an empty maze anyway.
        level_stars = dict(profile.get("level_stars", {}))
        level_key = str(replay_level)
        previous_best_stars = level_stars.get(level_key, 0)

        if not failed and stars_earned > previous_best_stars:
            beat_record = True
            extra_stars = stars_earned - previous_best_stars
            bounty_gold = calculate_star_bounty(extra_stars, difficulty)

        net_gold_gain = bounty_gold
    else:
        # ── STANDARD PROGRESSION: unchanged behavior ────────────────────
        if exp_result["flawless_bonus_eligible"] and not failed:
            # Flawless run: +30% of collected gold as bonus
            bonus_gold = int(gold_collected * 0.30)
        net_gold_gain = gold_collected + bonus_gold

    # DEFEAT PENALTY: Deduct a nominal percentage of currently HELD soft currency.
    # Spec: "only a nominal percentage of currently held soft currency is deducted."
    # Permanent upgrades and EXP are NEVER penalized. Applies identically on
    # replay defeats — replaying a lower level still carries real stakes.
    DEFEAT_GOLD_PENALTY_PCT = 0.10  # 10% of current gold balance lost on death
    gold_penalty = 0
    if failed:
        gold_penalty = int(profile.get("gold", 0) * DEFEAT_GOLD_PENALTY_PCT)

    # ── PROFILE UPDATES (atomic single write) ───────────────────────────
    new_total_exp = profile.get("total_exp", 0) + exp_earned
    new_gold = max(0, profile.get("gold", 0) + net_gold_gain - gold_penalty)
    new_diamonds = profile.get("diamonds", 0) + diamonds_collected

    # ── STAR TRACKING ─────────────────────────────────────────────────────
    # We track the BEST star rating achieved per level so the Level Progression
    # Panel can display it. On a STANDARD run, the level the player JUST played
    # is the current_level (before any EXP-induced level-up from this run). On
    # a REPLAY run, it's the explicit replay_level instead — this is the
    # "High-Water Mark Star Tracking" rule: the stored value can only go up,
    # never down, whether the source is a fresh clear or a replay attempt.
    current_level = exp_to_level(profile.get("total_exp", 0))
    level_stars = dict(profile.get("level_stars", {}))

    target_level_key = str(replay_level) if is_replay else str(current_level)
    if not failed and stars_earned > 0:
        existing_best = level_stars.get(target_level_key, 0)
        if stars_earned > existing_best:
            level_stars[target_level_key] = stars_earned

    updates = {
        "total_exp": new_total_exp,
        "gold": new_gold,
        "diamonds": new_diamonds,
        "level_stars": level_stars,
    }
    # FREEZE SPELL FIX: only touch freeze_spells_held when the client actually
    # reported an end-of-run count — omitting the key entirely (rather than
    # writing back the stale value) keeps this endpoint backward-compatible
    # with any caller that doesn't send `spells_remaining`.
    if spells_remaining is not None:
        updates["freeze_spells_held"] = spells_remaining

    updated_profile = update_profile(player_id, updates)

    # ── APPEND EXP HISTORY ────────────────────────────────────────────────
    # Only append to history on successful, NON-REPLAY runs. Replay runs
    # always have exp_earned == 0 by design (see above), so this check is
    # naturally also a no-op for them — but the explicit `not is_replay`
    # guard keeps the intent unambiguous and future-proof.
    if not is_replay and not failed and exp_earned > 0:
        updated_profile = append_exp_history(player_id, exp_earned)

    # ── RESPONSE PAYLOAD ─────────────────────────────────────────────────
    new_level = exp_to_level(new_total_exp)

    return success({
        "run_result": {
            "failed": failed,
            "verdict": exp_result["verdict"],
            "exp_earned": exp_earned,
            "stars_earned": stars_earned,
            "exp_breakdown": exp_result["breakdown"],
            "gold_collected": gold_collected,
            "bonus_gold": bonus_gold,
            "gold_penalty": gold_penalty,
            "diamonds_collected": diamonds_collected,
            "flawless": exp_result["flawless_bonus_eligible"],
            "is_replay": is_replay,
            "replay_level": replay_level,
            "bounty_gold": bounty_gold,
            "beat_record": beat_record,
            "previous_best_stars": previous_best_stars,
        },
        "player_state": {
            "total_exp": new_total_exp,
            "current_level": new_level,
            "gold": new_gold,
            "diamonds": new_diamonds,
            "exp_history": updated_profile.get("exp_history", []),
            "level_stars": level_stars,
            # FREEZE SPELL FIX: lets ResultTablet's `setPlayer((p) => ({ ...p,
            # ...player_state }))` immediately reflect the correct held count
            # without waiting for a separate profile refetch.
            "freeze_spells_held": updated_profile.get("freeze_spells_held", profile.get("freeze_spells_held", 0)),
        },
    })


@game_bp.route("/path_reveal_cost", methods=["POST"])
def path_reveal_cost():
    """
    POST /game/path_reveal_cost
    Returns the Diamond cost to use the 'Reveal Exit Path' emergency feature.

    The cost scales with maze difficulty and grid size, preventing
    cheap exploits on hard, large levels.

    Called: When the player taps the "Reveal Exit Path" button in-game,
    BEFORE the confirmation prompt is shown (so the UI can display the cost).

    Body:
    {
      "player_id": "uuid-string",
      "grid_rows": 30,
      "grid_cols": 30,
      "difficulty": 0.75
    }
    """
    body = request.get_json(silent=True) or {}
    missing = require_fields(body, "player_id", "grid_rows", "grid_cols", "difficulty")
    if missing:
        return error("missing_field", f"Required field missing: {missing}")

    player_id = body["player_id"]
    profile = get_profile(player_id)
    if not profile:
        return error("player_not_found", f"No player with ID: {player_id}", 404)

    rows = safe_int(body["grid_rows"], 10)
    cols = safe_int(body["grid_cols"], 10)
    difficulty = clamp(safe_float(body["difficulty"], 0.0), 0.0, 1.0)

    cost = _calculate_reveal_cost(rows, cols, difficulty)
    can_afford = profile.get("diamonds", 0) >= cost

    return success({
        "diamond_cost": cost,
        "player_diamonds": profile.get("diamonds", 0),
        "can_afford": can_afford,
    })


@game_bp.route("/purchase_path_reveal", methods=["POST"])
def purchase_path_reveal():
    """
    POST /game/purchase_path_reveal
    Processes the Diamond payment for the 'Reveal Exit Path' feature.

    Called: After the player confirms the cost prompt in-game.
    The frontend then renders the golden path trail.

    Body:
    {
      "player_id": "uuid-string",
      "grid_rows": 30,
      "grid_cols": 30,
      "difficulty": 0.75
    }
    """
    body = request.get_json(silent=True) or {}
    missing = require_fields(body, "player_id", "grid_rows", "grid_cols", "difficulty")
    if missing:
        return error("missing_field", f"Required field missing: {missing}")

    player_id = body["player_id"]
    profile = get_profile(player_id)
    if not profile:
        return error("player_not_found", f"No player with ID: {player_id}", 404)

    rows = safe_int(body["grid_rows"], 10)
    cols = safe_int(body["grid_cols"], 10)
    difficulty = clamp(safe_float(body["difficulty"], 0.0), 0.0, 1.0)

    cost = _calculate_reveal_cost(rows, cols, difficulty)
    current_diamonds = profile.get("diamonds", 0)

    if current_diamonds < cost:
        return error(
            "insufficient_diamonds",
            f"Not enough Diamonds. Required: {cost}, Have: {current_diamonds}",
            402
        )

    new_diamonds = current_diamonds - cost
    update_profile(player_id, {"diamonds": new_diamonds})

    return success({
        "success": True,
        "diamonds_spent": cost,
        "diamonds_remaining": new_diamonds,
        "reveal_duration_seconds": 5,  # Spec: path visible for 5 seconds
    })


# ──────────────────────────────────────────────
# PRIVATE HELPERS
# ──────────────────────────────────────────────

def _calculate_reveal_cost(rows: int, cols: int, difficulty: float) -> int:
    """
    Path Reveal Diamond cost formula.

    WHY SCALE WITH SIZE AND DIFFICULTY:
    A path reveal on a tiny easy maze is nearly useless — cheap is fair.
    On a massive hard maze, it's a game-saving emergency tool — costly is fair.
    This prevents rich players from trivializing endgame levels cheaply.

    Formula:
      base = 5 diamonds
      size_factor = sqrt(rows * cols) / 10   (≈ 1.0 for 10x10, ≈ 4.2 for 40x40)
      difficulty_factor = 1.0 + difficulty   (1.0 → 2.0)
      cost = ceil(base * size_factor * difficulty_factor)
    """
    base = 5
    size_factor = math.sqrt(rows * cols) / 10
    difficulty_factor = 1.0 + difficulty
    return max(1, math.ceil(base * size_factor * difficulty_factor))


def _get_freeze_duration(profile: dict) -> float:
    """Returns the player's current freeze spell duration in seconds."""
    from core.shop_matrix import get_freeze_upgrade_tier
    tier = profile.get("freeze_spell_level", 1)
    cfg = get_freeze_upgrade_tier(tier)
    return cfg["freeze_duration_seconds"] if cfg else 1.5


def _get_max_integrity(profile: dict) -> int:
    """Returns the player's max integrity percentage (e.g., 150)."""
    from core.shop_matrix import get_integrity_tier
    tier = profile.get("integrity_level", 0)
    cfg = get_integrity_tier(tier)
    return cfg["max_integrity_pct"] if cfg else 100


def _get_velocity(profile: dict) -> float:
    """Returns the player's velocity multiplier (e.g., 1.42)."""
    from core.shop_matrix import get_velocity_tier
    tier = profile.get("velocity_level", 0)
    cfg = get_velocity_tier(tier)
    return cfg["speed_value"] if cfg else 1.0
