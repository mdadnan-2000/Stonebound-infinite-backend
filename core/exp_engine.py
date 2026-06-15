"""
core/exp_engine.py
===================
Performance-based EXP calculation for Stonebound: Infinite.

WHY PERFORMANCE-BASED EXP:
A flat EXP reward punishes cautious players and rewards cheese strategies.
Instead, we evaluate FOUR performance axes and multiply them together,
so a player must excel across all dimensions to earn maximum EXP.

The multiplication model means: excelling in one area cannot fully
compensate for terrible performance in another. A player who was
lightning-fast but took severe damage earns moderate EXP — not maximum.
"""

import math


# ──────────────────────────────────────────────
# BASE EXP TABLE
# Base EXP scales with difficulty so late-game levels feel worth grinding.
# ──────────────────────────────────────────────
BASE_EXP_MIN = 100   # Minimum possible base EXP (easiest level)
BASE_EXP_MAX = 1500  # Maximum possible base EXP (hardest level)


# ──────────────────────────────────────────────
# PERFORMANCE MULTIPLIER FLOORS
# Each multiplier is clamped to a minimum so a bad run still gives
# some EXP (except failure — see below). Nobody likes zero for trying.
# ──────────────────────────────────────────────
MULTIPLIER_FLOOR = 0.1   # Worst possible multiplier per axis
MULTIPLIER_CEIL  = 1.0   # Best possible multiplier per axis (1.0 = no bonus)

# Bonus Gold thresholds for the "flawless" bonus shown in Results UI
FLAWLESS_BOMB_AVOIDANCE = True   # No bomb damage at all
FLAWLESS_DAMAGE_THRESHOLD = 0.0  # Zero integrity lost
FLAWLESS_BONUS_GOLD_PCT = 0.30   # +30% of collected gold as bonus


def _time_multiplier(elapsed_seconds: int, par_time_seconds: int) -> float:
    """
    Rewards fast completion relative to a 'par time' derived from grid size.

    WHY PAR TIME:
    A fixed time limit would punish large maps unfairly. Instead, we define
    a par time proportional to the grid area, giving fast players a bonus
    and very slow players a penalty.

    Scoring:
      - Completed in ≤ 50% of par time: 1.0 (full score)
      - Completed at par time: 0.6
      - Completed at 2× par time or more: MULTIPLIER_FLOOR
    """
    if par_time_seconds <= 0:
        return MULTIPLIER_FLOOR
    ratio = elapsed_seconds / par_time_seconds
    # Exponential decay: multiplier = 1.0 * exp(-k * ratio), tuned so par_time gives 0.6
    k = -math.log(0.6)  # ≈ 0.511
    score = math.exp(-k * ratio)
    return round(max(MULTIPLIER_FLOOR, min(MULTIPLIER_CEIL, score)), 4)


def _damage_multiplier(integrity_lost_pct: float) -> float:
    """
    Rewards avoiding damage throughout the run.

    integrity_lost_pct: 0.0 (no damage taken) to 1.0 (lost all health).

    Scoring:
      - 0% damage: 1.0
      - 50% damage: ~0.5
      - 100% damage (survived on last breath): MULTIPLIER_FLOOR
    """
    score = 1.0 - (integrity_lost_pct * (1.0 - MULTIPLIER_FLOOR))
    return round(max(MULTIPLIER_FLOOR, min(MULTIPLIER_CEIL, score)), 4)


def _backtrack_multiplier(backtrack_steps: int, total_steps: int) -> float:
    """
    Penalizes excessive backtracking (poor navigation).

    backtrack_steps: Steps taken in the reverse direction from the optimal route.
    total_steps: Total steps taken during the run.

    WHY BACKTRACKING MATTERS:
    A player who found the exit efficiently is rewarded. A player who wandered
    aimlessly and fluked into the exit earns less.

    Scoring:
      - 0% backtrack: 1.0
      - 30% backtrack: ~0.5
      - 60%+ backtrack: MULTIPLIER_FLOOR
    """
    if total_steps <= 0:
        return MULTIPLIER_FLOOR
    ratio = min(1.0, backtrack_steps / total_steps)
    score = 1.0 - (ratio / 0.6) * (1.0 - MULTIPLIER_FLOOR)
    return round(max(MULTIPLIER_FLOOR, min(MULTIPLIER_CEIL, score)), 4)


def _loot_multiplier(loot_collected_pct: float) -> float:
    """
    Minor bonus for thoroughness — collecting a high % of available loot.
    This is the weakest multiplier; it acts as a tiebreaker, not a dominant factor.

    loot_collected_pct: Fraction of total loot collected (0.0–1.0).
    """
    # Linear: 0% loot = 0.5, 100% loot = 1.0
    score = 0.5 + 0.5 * loot_collected_pct
    return round(max(MULTIPLIER_FLOOR, min(MULTIPLIER_CEIL, score)), 4)


def compute_par_time(rows: int, cols: int) -> int:
    """
    Computes the 'par time' (expected completion time in seconds) for a maze.

    WHY SQRT OF AREA:
    A 30x30 maze has 900 cells, but the player doesn't visit every cell.
    The expected path length grows roughly with sqrt(area), so we use that
    as our time baseline with a generous 2-second-per-cell movement budget.
    """
    cell_count = rows * cols
    expected_path_length = math.sqrt(cell_count)
    seconds_per_step = 2.0  # Generous budget to account for thinking/exploring
    return int(expected_path_length * seconds_per_step)


def calculate_exp_reward(
    difficulty: float,
    elapsed_seconds: int,
    rows: int,
    cols: int,
    integrity_lost_pct: float,
    backtrack_steps: int,
    total_steps: int,
    loot_collected_pct: float,
    failed: bool,
) -> dict:
    """
    Master EXP calculation function.

    FAILURE HANDLING:
    If the player's Integrity hits 0%, `failed=True`. They earn 0 EXP.
    Currencies collected BEFORE death are retained (handled at API level).

    Returns a structured dict with the raw EXP value, all multiplier
    components, performance verdict, and bonus gold eligibility flag.
    """

    # ── FAILURE STATE ──────────────────────────────────────────────────────
    if failed:
        return {
            "exp_earned": 0,
            "failed": True,
            "verdict": "Defeated",
            "breakdown": {
                "base_exp": 0,
                "time_multiplier": 0,
                "damage_multiplier": 0,
                "backtrack_multiplier": 0,
                "loot_multiplier": 0,
            },
            "flawless_bonus_eligible": False,
        }

    # ── BASE EXP (scales with difficulty) ─────────────────────────────────
    base_exp = int(BASE_EXP_MIN + (BASE_EXP_MAX - BASE_EXP_MIN) * difficulty)

    # ── INDIVIDUAL MULTIPLIERS ─────────────────────────────────────────────
    par_time = compute_par_time(rows, cols)
    t_mult   = _time_multiplier(elapsed_seconds, par_time)
    d_mult   = _damage_multiplier(integrity_lost_pct)
    b_mult   = _backtrack_multiplier(backtrack_steps, total_steps)
    l_mult   = _loot_multiplier(loot_collected_pct)

    # ── COMPOSITE MULTIPLIER ───────────────────────────────────────────────
    # All four axes multiplied together — weakness in any area compounds downward.
    composite = t_mult * d_mult * b_mult * l_mult

    # ── FINAL EXP ─────────────────────────────────────────────────────────
    exp_earned = max(1, int(base_exp * composite))  # Always at least 1 on success

    # ── PERFORMANCE VERDICT ────────────────────────────────────────────────
    # Composite score thresholds map to UI praise text shown on Results Screen.
    if composite >= 0.75:
        verdict = "Masterful"
    elif composite >= 0.50:
        verdict = "Excellent"
    elif composite >= 0.30:
        verdict = "Passable"
    else:
        verdict = "Barely Survived"

    # ── FLAWLESS BONUS GOLD ELIGIBILITY ───────────────────────────────────
    # Bonus gold (shown separately in Results UI) if zero damage taken
    flawless = (integrity_lost_pct == 0.0)

    return {
        "exp_earned": exp_earned,
        "failed": False,
        "verdict": verdict,
        "breakdown": {
            "base_exp": base_exp,
            "time_multiplier": t_mult,
            "damage_multiplier": d_mult,
            "backtrack_multiplier": b_mult,
            "loot_multiplier": l_mult,
            "composite_multiplier": round(composite, 4),
        },
        "flawless_bonus_eligible": flawless,
    }
