"""
core/maze_engine.py
====================
Procedural maze generator for Stonebound: Infinite.

WHY THIS APPROACH (Recursive Backtracker / DFS):
- Produces perfect mazes (every cell reachable, exactly one path between any two cells).
- Dead ends are a natural byproduct — no extra logic needed to create them.
- After generation, we inject loops by removing extra walls, giving Chasers
  multiple flanking routes (the "junction loops" mechanic).

GRID ENCODING:
  0 = open path (floor tile the player can traverse)
  1 = wall block (solid stone, blocks movement and explosion propagation)

COORDINATE SYSTEM:
  grid[row][col] — row 0 is the top, increasing downward.
  (row, col) is used throughout; the frontend can map this to (x, y) as needed.
"""

import random
from collections import deque
from typing import List, Tuple, Dict, Any


# Cell states in the grid matrix
WALL = 1
FLOOR = 0


def _carve_path(grid: List[List[int]], rows: int, cols: int,
                start_row: int, start_col: int, rng: random.Random) -> None:
    """
    Recursive backtracker DFS maze carver.

    WHY IN-PLACE:
    Modifying the grid in-place avoids creating large intermediate copies.
    The grid is fully pre-filled with WALLs; this function only opens FLOORs.

    ALGORITHM:
    From the current cell, shuffle the 4 cardinal directions, then for each
    unvisited neighbor (2 steps away), carve through the wall between them
    and recurse. This creates a spanning tree = perfect maze.
    """
    # Use an explicit stack to avoid Python's default recursion limit on large grids
    stack = [(start_row, start_col)]
    visited = set()
    visited.add((start_row, start_col))
    grid[start_row][start_col] = FLOOR

    # Directions: (row_delta, col_delta) in increments of 2 (skipping the wall cell)
    directions = [(-2, 0), (2, 0), (0, -2), (0, 2)]

    while stack:
        r, c = stack[-1]
        rng.shuffle(directions)

        moved = False
        for dr, dc in directions:
            nr, nc = r + dr, c + dc
            if 0 < nr < rows - 1 and 0 < nc < cols - 1 and (nr, nc) not in visited:
                # Carve the wall between current cell and neighbor
                grid[r + dr // 2][c + dc // 2] = FLOOR
                grid[nr][nc] = FLOOR
                visited.add((nr, nc))
                stack.append((nr, nc))
                moved = True
                break

        if not moved:
            stack.pop()


def _inject_loops(grid: List[List[int]], rows: int, cols: int,
                  loop_freq: float, rng: random.Random) -> int:
    """
    After generating a perfect maze, randomly remove interior walls to
    create loop paths (multiple routes between cells).

    WHY LOOPS MATTER:
    A perfect maze has only one path between any two points — Chasers can
    always predict and block the player. Loops create the "junction loops"
    mechanic where the player can shake Chasers via alternate routes.

    loop_freq: Fraction of interior walls to attempt removing (0.0–0.25).
    Returns the count of loops actually created.
    """
    loops_created = 0
    # Collect all interior wall cells (not on the border)
    interior_walls = [
        (r, c)
        for r in range(1, rows - 1)
        for c in range(1, cols - 1)
        if grid[r][c] == WALL
    ]
    rng.shuffle(interior_walls)
    target = int(len(interior_walls) * loop_freq)

    for r, c in interior_walls[:target]:
        # Only remove if this wall separates two floor cells horizontally or vertically
        # (Prevents creating isolated 2x2 open blocks which look wrong)
        h_open = grid[r][c - 1] == FLOOR and grid[r][c + 1] == FLOOR
        v_open = grid[r - 1][c] == FLOOR and grid[r + 1][c] == FLOOR
        if h_open or v_open:
            grid[r][c] = FLOOR
            loops_created += 1

    return loops_created


def _count_dead_ends(grid: List[List[int]], rows: int, cols: int) -> int:
    """
    Counts cells with exactly one open neighbor (dead ends).

    WHY COUNT:
    The Loading Screen UI displays the dead-end count as a tactical intel
    metric. Dead ends = potential traps where the player can get cornered.
    """
    count = 0
    for r in range(1, rows - 1):
        for c in range(1, cols - 1):
            if grid[r][c] == FLOOR:
                open_neighbors = sum(
                    1 for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]
                    if grid[r + dr][c + dc] == FLOOR
                )
                if open_neighbors == 1:
                    count += 1
    return count


def _get_all_floor_cells(grid: List[List[int]], rows: int, cols: int) -> List[Tuple[int, int]]:
    """Returns a flat list of all (row, col) positions that are FLOOR tiles."""
    return [(r, c) for r in range(rows) for c in range(cols) if grid[r][c] == FLOOR]


def _bfs_distance(grid: List[List[int]], rows: int, cols: int,
                  start: Tuple[int, int]) -> Dict[Tuple[int, int], int]:
    """
    Breadth-first search from `start` to compute shortest path distances
    to every reachable floor cell.

    WHY BFS HERE (not A*):
    We don't need a path — we need distances for multiple purposes:
    1. Placing the exit as far as possible from the player spawn.
    2. Verifying connectivity (all floor cells reachable).
    BFS gives us all distances in O(V+E) in one pass.
    """
    dist = {start: 0}
    queue = deque([start])
    directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]

    while queue:
        r, c = queue.popleft()
        for dr, dc in directions:
            nr, nc = r + dr, c + dc
            if (0 <= nr < rows and 0 <= nc < cols
                    and grid[nr][nc] == FLOOR
                    and (nr, nc) not in dist):
                dist[(nr, nc)] = dist[(r, c)] + 1
                queue.append((nr, nc))

    return dist


def _place_entities(floor_cells: List[Tuple[int, int]],
                    exclude: List[Tuple[int, int]],
                    count: int,
                    rng: random.Random,
                    min_dist_from: Dict[Tuple[int, int], int] = None,
                    min_dist: int = 0) -> List[Tuple[int, int]]:
    """
    Places `count` entities on random floor cells, avoiding `exclude` positions
    and optionally enforcing a minimum BFS distance from a reference point.

    WHY MIN DISTANCE:
    - Bombs near the player spawn = unfair instant death.
    - Chasers near spawn = no reaction time.
    - Exit too close to spawn = trivially short level.
    This ensures a minimum "breathing room" radius around spawn.
    """
    exclude_set = set(exclude)
    candidates = [
        cell for cell in floor_cells
        if cell not in exclude_set
        and (min_dist_from is None or min_dist_from.get(cell, 0) >= min_dist)
    ]
    rng.shuffle(candidates)
    return candidates[:count]


def generate_maze(params: dict, seed: int = None) -> dict:
    """
    Master maze generation function. Accepts level parameters from the
    progression engine and returns a complete maze payload.

    PAYLOAD STRUCTURE (what the frontend receives):
    - grid: 2D array of 0/1 values
    - metadata: grid dimensions, dead ends, loops, branch factor, threat rating
    - spawn: player starting coordinates
    - exit: exit door coordinates
    - loot: positions of gold, diamonds, medicine, spells
    - hazards: bomb positions and chaser SPAWN positions
      (NOT real-time chaser positions — the frontend handles live movement)

    WHY WE SEND SPAWN COORDINATES (NOT LIVE POSITIONS) FOR CHASERS:
    The backend has no game loop. Chasers move in real-time on the client.
    The backend only provides the starting grid state; the frontend's
    pathfinding engine drives all subsequent entity movement.
    """
    rng = random.Random(seed)  # Deterministic generation if seed provided

    rows = params["grid"]["rows"]
    cols = params["grid"]["cols"]
    loop_freq = params["loop_freq"]
    loot_cfg = params["loot"]
    hazard_cfg = params["hazards"]

    # ── STEP 1: Initialize grid full of walls ──────────────────────────────
    # Odd-dimension grids ensure clean cell/wall alternation for the algorithm
    grid = [[WALL] * cols for _ in range(rows)]

    # ── STEP 2: Carve the maze ─────────────────────────────────────────────
    # Start from (1,1) — safely inside the border
    _carve_path(grid, rows, cols, 1, 1, rng)

    # ── STEP 3: Inject loops (junction loops mechanic) ─────────────────────
    loops_created = _inject_loops(grid, rows, cols, loop_freq, rng)

    # ── STEP 4: Gather all walkable cells ──────────────────────────────────
    floor_cells = _get_all_floor_cells(grid, rows, cols)

    # ── STEP 5: Player spawn at (1, 1) ────────────────────────────────────
    spawn = (1, 1)

    # ── STEP 6: BFS from spawn to find distances ──────────────────────────
    dist_from_spawn = _bfs_distance(grid, rows, cols, spawn)

    # ── STEP 7: Place exit at the farthest reachable cell ─────────────────
    # WHY FARTHEST: Ensures the player must actually traverse the maze.
    reachable = [(d, cell) for cell, d in dist_from_spawn.items()]
    reachable.sort(reverse=True)
    exit_pos = reachable[0][1] if reachable else (rows - 2, cols - 2)

    occupied = [spawn, exit_pos]

    # ── STEP 8: Place loot (must be MIN_LOOT_DIST from spawn) ─────────────
    MIN_LOOT_DIST = 3  # Avoid trivial instant collection at spawn

    gold_positions = _place_entities(
        floor_cells, occupied, loot_cfg["gold_count"], rng,
        dist_from_spawn, MIN_LOOT_DIST
    )
    occupied += gold_positions

    diamond_positions = _place_entities(
        floor_cells, occupied, loot_cfg["diamond_count"], rng,
        dist_from_spawn, MIN_LOOT_DIST
    )
    occupied += diamond_positions

    medicine_positions = _place_entities(
        floor_cells, occupied, loot_cfg["medicine_count"], rng,
        dist_from_spawn, MIN_LOOT_DIST
    )
    occupied += medicine_positions

    spell_positions = _place_entities(
        floor_cells, occupied, loot_cfg["spell_floor_drops"], rng,
        dist_from_spawn, MIN_LOOT_DIST
    )
    occupied += spell_positions

    # ── STEP 9: Place hazards (bombs + chaser spawns) ─────────────────────
    # Bombs MUST be far from player spawn — no immediate detonation on game start.
    MIN_BOMB_DIST = 5

    bomb_positions = _place_entities(
        floor_cells, occupied, hazard_cfg["bomb_count"], rng,
        dist_from_spawn, MIN_BOMB_DIST
    )
    occupied += bomb_positions

    # Chaser spawn positions — also kept away from player start
    MIN_CHASER_DIST = 8

    chaser_spawns = _place_entities(
        floor_cells, occupied, hazard_cfg["initial_chaser_count"], rng,
        dist_from_spawn, MIN_CHASER_DIST
    )

    # ── STEP 10: Compute metadata metrics for Loading Screen ───────────────
    dead_end_count = _count_dead_ends(grid, rows, cols)

    return {
        "metadata": {
            "level_number": params["level_number"],
            "threat_rating": params["threat_rating"],
            "difficulty": params["difficulty"],
            "grid_rows": rows,
            "grid_cols": cols,
            "dead_end_count": dead_end_count,
            "junction_loop_count": loops_created,
            "branch_factor": params["branch_factor"],
            "chaser_spawn_interval_seconds": hazard_cfg["chaser_spawn_interval"],
        },
        "grid": grid,  # 2D array — the authoritative maze layout
        "spawn": {"row": spawn[0], "col": spawn[1]},
        "exit": {"row": exit_pos[0], "col": exit_pos[1]},
        "loot": {
            "gold": [{"row": r, "col": c} for r, c in gold_positions],
            "diamonds": [{"row": r, "col": c} for r, c in diamond_positions],
            "medicine": [{"row": r, "col": c} for r, c in medicine_positions],
            "spells": [{"row": r, "col": c} for r, c in spell_positions],
        },
        "hazards": {
            # Bomb positions are revealed upfront because the frontend needs them
            # to implement the "Amoeba Sense" BFS trigger logic client-side.
            # In a cheat-proof production build, you'd withhold these until triggered,
            # but for this architecture the frontend owns real-time hazard logic.
            "bombs": [{"row": r, "col": c} for r, c in bomb_positions],
            # Chaser SPAWN positions only — not live tracking (frontend handles movement)
            "chaser_spawns": [{"row": r, "col": c} for r, c in chaser_spawns],
        },
    }
