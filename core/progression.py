"""
core/progression.py
====================
Handles the infinite progression system for Stonebound: Infinite.

WHY THIS MODULE EXISTS:
The game must scale infinitely without breaking. Rather than hand-crafting level configs
for every possible level number, we use a mathematical pipeline:

    Total EXP  -->  Normalized Difficulty Float (0.0–1.0)  -->  Level Parameters

The Difficulty Float acts as a universal "heat dial" that every system reads from.
This means adding new mechanics later just means reading the same dial — no refactoring needed.

LEVEL REPLAY SUPPORT:
`generate_level_parameters` now accepts an optional `replay_level` override. When
provided, the difficulty dial is derived directly from that historical level number
(via `level_to_difficulty`) instead of from the player's current total EXP. This is
what guarantees a replayed level is generated with EXACTLY the same maze-complexity
parameters (grid size, loop factor, dead-end frequency, hazard density) it had the
first time the player faced it — fulfilling the "Fixed Environment Complexity" rule.
The player's CURRENT upgrades (velocity, integrity, freeze spells) are layered on top
via `player_snapshot` in the API layer, untouched by this module.
"""

import math


# ──────────────────────────────────────────────
# EXP CURVE CONSTANTS
# ──────────────────────────────────────────────

# EXP required for level N uses a polynomial growth formula:
#   EXP(n) = BASE * (n ^ EXPONENT)
# This keeps early levels fast and fun while making late levels feel earned.
EXP_BASE_PER_LEVEL = 300
EXP_LEVEL_EXPONENT = 1.6  # Steeper than linear, softer than quadratic

# Difficulty saturates at a "soft cap" level. Beyond this, difficulty
# still increments but very slowly — prevents the game from becoming unplayable.
DIFFICULTY_SOFT_CAP_LEVEL = 50
DIFFICULTY_HARD_CAP = 1.0  # Absolute ceiling for the difficulty float


# ──────────────────────────────────────────────
# THREAT RATING THRESHOLDS
# Difficulty Float --> Human-readable categorical tier shown on Loading Screen.
# ──────────────────────────────────────────────
THREAT_TIERS = [
    (0.0,  "Stable"),      # Tutorial zone: forgiving layouts, sparse hazards
    (0.25, "Perilous"),    # Mid-game: traps become meaningful threats
    (0.55, "Torment"),     # Late-game: aggressive chasers, dense dead-ends
    (0.80, "Oblivion"),    # Endgame: near-max hazards, punishing grid size
]


def exp_for_level(level: int) -> int:
    """
    Returns the CUMULATIVE total EXP required to REACH a given level.

    WHY CUMULATIVE:
    Storing/comparing cumulative EXP is simpler and more reliable than
    tracking "EXP within current level". It avoids state desync bugs.
    """
    if level <= 1:
        return 0
    return int(EXP_BASE_PER_LEVEL * (level ** EXP_LEVEL_EXPONENT))


def exp_to_level(total_exp: int) -> int:
    """
    Reverse maps total EXP back to a level number.
    We iterate because the inverse of a polynomial has no clean closed form,
    and levels are bounded enough that iteration is fast.
    """
    level = 1
    while exp_for_level(level + 1) <= total_exp:
        level += 1
    return level


def level_to_difficulty(level: int) -> float:
    """
    Converts a raw LEVEL NUMBER directly into a normalized difficulty float
    in [0.0, 1.0], independent of any particular player's total EXP.

    WHY THIS EXISTS (separate from `exp_to_difficulty`):
    Difficulty has always been a pure function of level number — `exp_to_difficulty`
    only adds the EXP->level lookup on top. Exposing this directly lets the
    Level Replay feature recompute the EXACT original difficulty for a level
    number a player has already passed, without needing their current EXP at all.

    WHY LOGARITHMIC:
    Log curves feel "natural" for progression — early levels scale fast,
    late levels feel like grinding toward a ceiling. This matches player expectations.
    """
    raw = math.log1p(max(1, level)) / math.log1p(DIFFICULTY_SOFT_CAP_LEVEL)
    return min(raw, DIFFICULTY_HARD_CAP)


def exp_to_difficulty(total_exp: int) -> float:
    """
    Converts raw EXP into a normalized difficulty float in [0.0, 1.0].

    APPROACH:
    1. Map EXP -> level number.
    2. Delegate to `level_to_difficulty` for the log-smoothing step.
    """
    level = exp_to_level(total_exp)
    return level_to_difficulty(level)


def difficulty_to_threat_rating(difficulty: float) -> str:
    """
    Maps the difficulty float to a human-readable Threat Rating string.
    Iterates the tier list in reverse to find the highest tier the
    difficulty qualifies for.
    """
    rating = "Stable"
    for threshold, label in THREAT_TIERS:
        if difficulty >= threshold:
            rating = label
    return rating


def generate_level_parameters(total_exp: int, replay_level: int = None) -> dict:
    """
    Master function: given a player's total EXP, returns the full
    set of parameters needed to generate the next maze level.

    ALL difficulty-derived values live here so the maze generator
    (maze_engine.py) stays clean and only deals with grid logic.

    Returns a structured dict consumed by the maze generator and
    passed through the API to the Loading Screen UI.

    LEVEL REPLAY OVERRIDE:
    If `replay_level` is provided, the difficulty dial (and therefore every
    derived parameter — grid size, dead ends, loops, loot, hazards) is computed
    from THAT level number instead of the player's current progression. This is
    the single source of truth that guarantees a replay's "Fixed Environment
    Complexity" exactly matches what the level originally was, with no
    hardcoded per-level tables. The standard (non-replay) progression path
    below is completely untouched.
    """
    if replay_level is not None:
        # ── REPLAY PATH: difficulty pinned to the historical level number ──
        difficulty = level_to_difficulty(replay_level)
        level_number = replay_level
    else:
        # ── STANDARD PROGRESSION PATH (unchanged) ──────────────────────────
        difficulty = exp_to_difficulty(total_exp)
        level_number = exp_to_level(total_exp) + 1  # Next level to play

    # ── GRID SIZE ──────────────────────────────────────────────────────────
    # Starts at 10x10 (tiny, tutorial) and scales up to 40x40 (massive arena).
    # Capped to keep maze generation time reasonable.
    MIN_GRID, MAX_GRID = 10, 40
    grid_size = int(MIN_GRID + (MAX_GRID - MIN_GRID) * difficulty)
    # Ensure odd dimensions so the recursive backtracker algorithm works cleanly
    if grid_size % 2 == 0:
        grid_size += 1
    rows = grid_size
    cols = grid_size

    # ── DEAD END FREQUENCY ─────────────────────────────────────────────────
    # Dead ends are created by NOT removing a wall during generation.
    # Range: 0.1 (very few traps) to 0.55 (more than half paths are dead ends)
    dead_end_freq = round(0.1 + 0.45 * difficulty, 3)

    # ── BRANCH FACTOR ──────────────────────────────────────────────────────
    # Higher = more complex corridor branching. Displayed on Loading Screen.
    # Range: 1.0 (simple) to 2.0 (highly complex)
    branch_factor = round(1.0 + 1.0 * difficulty, 2)

    # ── LOOP FREQUENCY ─────────────────────────────────────────────────────
    # After maze generation, we remove extra walls to create loops (multiple paths).
    # Range: 0.0 (perfect maze) to 0.25 (heavily looped)
    loop_freq = round(0.0 + 0.25 * difficulty, 3)

    # ── LOOT AMOUNTS ───────────────────────────────────────────────────────
    # More gold at higher difficulty to compensate for the harder challenge.
    # Diamonds are rarer and scale more slowly.
    # NOTE: For Level Replay runs, the API layer (game_routes.py) zeroes these
    # out AFTER this function returns — implementing the "Empty Maze" rule
    # without duplicating or hardcoding any of the scaling math here.
    gold_count = int(5 + 30 * difficulty)
    diamond_count = int(0 + 5 * difficulty)

    # ── HAZARD INTENSITY ───────────────────────────────────────────────────
    # How many bombs and chasers are seeded into the maze.
    bomb_count = int(0 + 25 * difficulty)
    initial_chaser_count = int(0 + 4 * difficulty)  # Spawned at level start
    # Subsequent chasers spawn on a timer (interval in seconds, decreasing)
    chaser_spawn_interval = max(5, int(30 - 20 * difficulty))

    # ── MEDICINE BOX COUNT ─────────────────────────────────────────────────
    # Fewer health pickups at higher difficulty
    medicine_count = max(1, int(4 - 3 * difficulty))

    # ── FREEZING SPELL FLOOR DROPS ─────────────────────────────────────────
    # Chance to find a spell in the maze (not purchased). Higher difficulty = more help
    spell_floor_drops = int(0 + 3 * difficulty)

    return {
        "level_number": level_number,
        "difficulty": round(difficulty, 4),
        "threat_rating": difficulty_to_threat_rating(difficulty),
        "grid": {
            "rows": rows,
            "cols": cols,
        },
        "dead_end_freq": dead_end_freq,
        "branch_factor": branch_factor,
        "loop_freq": loop_freq,
        "loot": {
            "gold_count": gold_count,
            "diamond_count": diamond_count,
            "medicine_count": medicine_count,
            "spell_floor_drops": spell_floor_drops,
        },
        "hazards": {
            "bomb_count": bomb_count,
            "initial_chaser_count": initial_chaser_count,
            "chaser_spawn_interval": chaser_spawn_interval,
        },
    }
