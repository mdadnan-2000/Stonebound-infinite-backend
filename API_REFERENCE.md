# Stonebound: Infinite — API Reference

**Backend:** Python / Flask  
**Base URL (dev):** `http://localhost:5000`  
**Content-Type:** All requests and responses use `application/json`

---

## Response Envelope

Every endpoint returns the same outer wrapper:

```json
{
  "ok": true,
  "data": { ... },
  "error": null
}
```

On failure:

```json
{
  "ok": false,
  "data": null,
  "error": {
    "code": "insufficient_gold",
    "message": "Not enough Gold. Required: 300, Have: 150"
  }
}
```

All `data` payloads documented below are the value of `data` inside this envelope.

---

## Common Error Codes

| Code | HTTP | Meaning |
|------|------|---------|
| `missing_field` | 400 | Required body field absent |
| `player_not_found` | 404 | No profile with given player_id |
| `invalid_name` | 400 | Name is empty or not a string |
| `name_too_long` | 400 | Name exceeds 30 characters |
| `max_tier_reached` | 400 | Upgrade already at maximum tier |
| `insufficient_gold` | 402 | Player lacks required Gold |
| `insufficient_diamonds` | 402 | Player lacks required Diamonds |
| `carry_limit_reached` | 409 | Spell inventory is full |
| `not_found` | 404 | Endpoint URL doesn't exist |
| `internal_error` | 500 | Unexpected server error |

---

## Utility Endpoints

### `GET /health`

Liveness check.

**Response:**
```json
{
  "ok": true,
  "service": "Stonebound: Infinite API",
  "version": "1.0.0"
}
```

**Frontend Usage:** Poll on app startup to confirm the backend is reachable before showing the Intro UI.

---

### `GET /`

Lists all registered routes.

**Frontend Usage:** Debugging only.

---

## Player Endpoints

### `POST /player/create`

Creates a new player profile. Returns a UUID-based `player_id` that the frontend must persist locally (e.g., `localStorage`) and include in all subsequent requests.

**Request Body (all optional):**
```json
{
  "name": "Wayfarer"
}
```

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `name` | string | `"Wayfarer"` | 1–30 characters |

**Success Response (201):**
```json
{
  "player_id": "a1b2c3d4-...",
  "name": "Wayfarer",
  "avatar_frame_id": 1,
  "total_exp": 0,
  "gold": 500,
  "diamonds": 5,
  "integrity_level": 0,
  "velocity_level": 0,
  "freeze_spell_level": 1,
  "freeze_spells_held": 0,
  "exp_history": [],
  "current_level": 1,
  "exp_in_current_level": 0,
  "exp_to_next_level": 300,
  "next_level_total_exp": 300,
  "created_at": "2026-06-13T10:00:00+00:00",
  "updated_at": "2026-06-13T10:00:00+00:00"
}
```

**Frontend Usage:** Called once on first launch (if no `player_id` in localStorage). Store the returned `player_id` permanently.

---

### `GET /player/<player_id>`

Fetches the full player profile.

**Success Response (200):** Same shape as `POST /player/create` response.

**Computed Fields (not stored, derived from `total_exp`):**

| Field | Description |
|-------|-------------|
| `current_level` | Player's current level number |
| `exp_in_current_level` | EXP accumulated within the current level |
| `exp_to_next_level` | Total EXP required to reach the next level |
| `next_level_total_exp` | Absolute EXP threshold for next level |

**Frontend Usage:** Call on every app launch and after returning from a game run. Use to hydrate:
- Intro UI player card (name, avatar, level, EXP)
- Gold / Diamond counters
- Gear Status Matrix (upgrade levels, spell count)
- `exp_history` array → render the analytics line graph

---

### `PATCH /player/<player_id>/identity`

Updates the player's display name and/or avatar frame. Send only the fields you want to change.

**Request Body (at least one required):**
```json
{
  "name": "StoneLord",
  "avatar_frame_id": 3
}
```

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | 1–30 characters |
| `avatar_frame_id` | integer | Must be ≥ 1 |

**Success Response (200):** Full updated profile (same shape as GET).

**Frontend Usage:** Call when the player edits their name field or selects a new avatar frame on the Intro UI. Use the returned `name` and `avatar_frame_id` to update the displayed player card immediately.

---

### `GET /player/all`

Returns all stored player profiles.

**Success Response (200):**
```json
[
  { ...profile... },
  { ...profile... }
]
```

**Frontend Usage:** Debug/admin view only.

---

### `DELETE /player/<player_id>`

Permanently deletes a player profile.

**Success Response (200):**
```json
{
  "deleted": true,
  "player_id": "a1b2c3d4-..."
}
```

---

## Game Endpoints

### `POST /game/generate_level`

Generates a complete procedural maze level based on the player's current EXP. This is the core generation call — the backend runs the Recursive Backtracker algorithm and returns the full maze payload.

**Request Body:**
```json
{
  "player_id": "a1b2c3d4-...",
  "seed": 98765
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `player_id` | string | ✅ | Must be a valid profile ID |
| `seed` | integer | ❌ | Omit for random. Pass the same seed on retry to regenerate the identical maze. |

**Success Response (200):**
```json
{
  "maze": {
    "metadata": {
      "level_number": 14,
      "threat_rating": "Torment",
      "difficulty": 0.7843,
      "grid_rows": 30,
      "grid_cols": 30,
      "dead_end_count": 22,
      "junction_loop_count": 8,
      "branch_factor": 1.78,
      "chaser_spawn_interval_seconds": 10
    },
    "grid": [
      [1, 1, 1, 1, ...],
      [1, 0, 0, 0, ...],
      ...
    ],
    "spawn": { "row": 1, "col": 1 },
    "exit":  { "row": 28, "col": 27 },
    "loot": {
      "gold":     [{ "row": 5, "col": 3 }, ...],
      "diamonds": [{ "row": 14, "col": 20 }, ...],
      "medicine": [{ "row": 9, "col": 11 }, ...],
      "spells":   [{ "row": 22, "col": 7 }, ...]
    },
    "hazards": {
      "bombs": [
        { "row": 7, "col": 5 },
        ...
      ],
      "chaser_spawns": [
        { "row": 25, "col": 24 },
        ...
      ]
    }
  },
  "player_snapshot": {
    "freeze_spells_held": 2,
    "freeze_spell_level": 3,
    "freeze_duration_seconds": 2.5,
    "max_integrity_pct": 150,
    "velocity_multiplier": 1.42
  },
  "seed": 98765
}
```

**Grid Encoding:**
- `0` = Floor tile (walkable)
- `1` = Wall block (impassable)
- Grid is a 2D array indexed as `grid[row][col]`, row 0 at top

**Entity Coordinate Notes:**
- `spawn`: Player starting position
- `exit`: Exit door position
- `bombs`: All bomb positions are provided upfront so the frontend can implement the "Amoeba Sense" BFS trigger logic (3 winding-path-steps radius)
- `chaser_spawns`: **Starting positions only** — NOT live positions. The frontend's pathfinding engine handles all chaser movement frame-by-frame

**`player_snapshot` Fields:**

| Field | Description |
|-------|-------------|
| `freeze_spells_held` | Consumable spell count to initialize HUD |
| `freeze_spell_level` | Current spell tier |
| `freeze_duration_seconds` | How long freeze lasts when activated |
| `max_integrity_pct` | Player's max health (e.g., 150 = 150% = 1.5× base) |
| `velocity_multiplier` | Speed multiplier for the player sphere (e.g., 1.42) |

**Frontend Usage:**
1. Call on "Begin Run" button press (Intro UI → Loading UI)
2. Display `metadata` fields on the Loading Screen as they stream in during the 3-second countdown
3. Initialize the gameplay board using `grid`, `spawn`, `exit`, `loot`, `hazards`
4. Initialize HUD with `player_snapshot` values
5. Store the returned `seed` — pass it back as `seed` in this endpoint if the player retries

---

### `POST /game/complete_level`

Processes the end of a level run. Must be called when:
- Player sphere steps into the Exit Door (victory), OR
- Player Integrity reaches 0% (defeat)

This is a transactional endpoint — it atomically calculates EXP, updates all currency balances, and appends to the EXP history.

**Request Body:**
```json
{
  "player_id": "a1b2c3d4-...",
  "failed": false,
  "elapsed_seconds": 180,
  "grid_rows": 30,
  "grid_cols": 30,
  "difficulty": 0.7843,
  "integrity_lost_pct": 0.50,
  "backtrack_steps": 15,
  "total_steps": 120,
  "loot_collected_pct": 0.80,
  "gold_collected": 350,
  "diamonds_collected": 2
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `player_id` | string | ✅ | Player profile ID |
| `failed` | boolean | ✅ | `true` if Integrity hit 0% |
| `elapsed_seconds` | integer | ✅ | Total seconds from level start to end |
| `grid_rows` | integer | ✅ | From maze metadata (for par time calculation) |
| `grid_cols` | integer | ✅ | From maze metadata |
| `difficulty` | float | ✅ | From maze metadata (0.0–1.0) |
| `integrity_lost_pct` | float | ✅ | Fraction of max integrity lost (0.0 = no damage, 1.0 = death) |
| `backtrack_steps` | integer | ✅ | Steps taken away from optimal path |
| `total_steps` | integer | ✅ | Total movement steps taken |
| `loot_collected_pct` | float | ✅ | Fraction of total available loot collected (0.0–1.0) |
| `gold_collected` | integer | ✅ | Actual gold coins picked up this run |
| `diamonds_collected` | integer | ✅ | Actual diamonds picked up this run |

**Success Response (200):**
```json
{
  "run_result": {
    "failed": false,
    "verdict": "Excellent",
    "exp_earned": 500,
    "exp_breakdown": {
      "base_exp": 900,
      "time_multiplier": 0.82,
      "damage_multiplier": 0.60,
      "backtrack_multiplier": 0.88,
      "loot_multiplier": 0.90,
      "composite_multiplier": 0.3902
    },
    "gold_collected": 350,
    "bonus_gold": 105,
    "gold_penalty": 0,
    "diamonds_collected": 2,
    "flawless": false
  },
  "player_state": {
    "total_exp": 7500,
    "current_level": 14,
    "gold": 1705,
    "diamonds": 47,
    "exp_history": [120, 200, 380, 500]
  }
}
```

**Verdict Strings (for Game Result UI header):**

| `verdict` | Composite Multiplier |
|-----------|----------------------|
| `"Masterful"` | ≥ 0.75 |
| `"Excellent"` | ≥ 0.50 |
| `"Passable"` | ≥ 0.30 |
| `"Barely Survived"` | < 0.30 |
| `"Defeated"` | `failed: true` |

**EXP & Economy Rules:**
- **Victory:** EXP earned = `base_exp × composite_multiplier` (minimum 1)
- **Flawless Bonus Gold:** If `integrity_lost_pct == 0.0` and `failed == false`, `bonus_gold = gold_collected × 0.30`
- **Defeat:** `exp_earned = 0`. `gold_penalty = current_gold_balance × 0.10` (10% of held gold). Diamonds and upgrade levels are never penalized.
- `exp_history` is only appended when `exp_earned > 0` (success runs only)

**Frontend Usage:**
- Call immediately when win/loss condition is detected
- Use `run_result` to render the Game Result UI stone tablet:
  - Victory: show `verdict`, `exp_earned`, `gold_collected`, `bonus_gold`
  - Defeat: show "Defeated" proverb, 0 EXP, `gold_collected`, `gold_penalty`
- Use `player_state` to refresh the Intro UI when the player returns to courtyard
- Use `player_state.exp_history` to re-render the analytics line graph

---

### `POST /game/path_reveal_cost`

Returns the Diamond cost for the "Reveal Exit Path" emergency feature **before** prompting the player to confirm. The cost scales with maze size and difficulty.

**Request Body:**
```json
{
  "player_id": "a1b2c3d4-...",
  "grid_rows": 30,
  "grid_cols": 30,
  "difficulty": 0.7843
}
```

**Success Response (200):**
```json
{
  "diamond_cost": 10,
  "player_diamonds": 45,
  "can_afford": true
}
```

**Cost Formula:** `ceil(5 × sqrt(rows × cols) / 10 × (1 + difficulty))`  
Examples: 10×10 easy → ~5 diamonds | 40×40 hard → ~28 diamonds

**Frontend Usage:** Call when the player taps the `Reveal Exit Path` button. Display the cost in the confirmation prompt. Grey-out or disable the confirm button if `can_afford` is `false`.

---

### `POST /game/purchase_path_reveal`

Processes the Diamond payment for the path reveal after the player confirms.

**Request Body:** Same as `/game/path_reveal_cost`

**Success Response (200):**
```json
{
  "success": true,
  "diamonds_spent": 10,
  "diamonds_remaining": 35,
  "reveal_duration_seconds": 5
}
```

**Frontend Usage:** Call on confirm tap. Deduct `diamonds_spent` from the in-game HUD Diamond counter. Render the golden path trail. Start a client-side timer for `reveal_duration_seconds` (5s) after which the trail fades.

---

## Shop Endpoints

### `GET /shop/catalog`

Returns the complete Black Market item catalog with all tier configurations and costs. No authentication required.

**Success Response (200):**
```json
{
  "integrity_upgrades": [
    {
      "tier": 0, "label": "Standard", "max_integrity_pct": 100,
      "cost_gold": 0, "description": "..."
    },
    { "tier": 1, "label": "Reinforced", "max_integrity_pct": 125, "cost_gold": 300, "description": "..." },
    { "tier": 2, "label": "Fortified",  "max_integrity_pct": 150, "cost_gold": 600, "description": "..." },
    { "tier": 3, "label": "Reinforced", "max_integrity_pct": 175, "cost_gold": 800, "description": "..." },
    { "tier": 4, "label": "Indomitable","max_integrity_pct": 200, "cost_gold": 1500,"description": "..." }
  ],
  "velocity_upgrades": [
    { "tier": 0,  "label": "Dormant",   "speed_value": 1.00, "cost_gold": 0,    "description": "..." },
    { "tier": 1,  "label": "Awakening", "speed_value": 1.10, "cost_gold": 150,  "description": "..." },
    ...
    { "tier": 10, "label": "Apex",      "speed_value": 2.65, "cost_gold": 3000, "description": "..." }
  ],
  "freeze_spell_upgrades": [
    { "tier": 1, "label": "Glacial Shard", "freeze_duration_seconds": 1.5, "inventory_weight_pct": 50, "cost_diamonds": 0,   "description": "..." },
    { "tier": 2, "label": "Frost Veil",    "freeze_duration_seconds": 2.0, "inventory_weight_pct": 40, "cost_diamonds": 10,  "description": "..." },
    { "tier": 3, "label": "Cryo Pulse",    "freeze_duration_seconds": 2.5, "inventory_weight_pct": 25, "cost_diamonds": 25,  "description": "..." },
    { "tier": 4, "label": "Arctic Wave",   "freeze_duration_seconds": 3.5, "inventory_weight_pct": 20, "cost_diamonds": 50,  "description": "..." },
    { "tier": 5, "label": "Void Blizzard", "freeze_duration_seconds": 5.0, "inventory_weight_pct": 20, "cost_diamonds": 100, "description": "..." }
  ],
  "freeze_spell_purchase_costs": { "1": 75, "2": 120, "3": 180, "4": 250, "5": 350 },
  "max_integrity_tier": 4,
  "max_velocity_tier": 10,
  "max_freeze_upgrade_tier": 5
}
```

**Spell Carry Capacity:** `floor(100 / inventory_weight_pct)` — e.g., weight 25% → carry 4 spells.

**Frontend Usage:** Fetch once when the Black Market opens. Use to render all upgrade rows, item descriptions, and the On-Demand Inspection Slate (item detail popup). Never hardcode any costs or tiers on the frontend.

---

### `GET /shop/player_state/<player_id>`

Returns the player's current upgrade levels and currencies alongside the full catalog — each tier pre-annotated with affordability and unlock status. Single endpoint to hydrate the entire Black Market UI.

**Success Response (200):**
```json
{
  "player_currencies": { "gold": 1250, "diamonds": 45 },
  "current_upgrade_levels": {
    "integrity_level": 3,
    "velocity_level": 4,
    "freeze_spell_level": 2
  },
  "freeze_spells_held": 2,
  "max_spells_carriable": 2,
  "spell_purchase_cost_gold": 120,
  "catalog": {
    "integrity_upgrades": [
      {
        "tier": 0, "label": "Standard", "max_integrity_pct": 100,
        "cost_gold": 0, "description": "...",
        "is_current": false,
        "is_affordable": true,
        "is_unlocked": true
      },
      {
        "tier": 3, ...,
        "is_current": true,
        "is_affordable": true,
        "is_unlocked": true
      },
      {
        "tier": 4, ..., "cost_gold": 1500,
        "is_current": false,
        "is_affordable": false,
        "is_unlocked": false
      }
    ],
    "velocity_upgrades": [ ... ],
    "freeze_spell_upgrades": [ ... ]
  }
}
```

**Annotation Fields per Tier:**

| Field | Type | Meaning |
|-------|------|---------|
| `is_current` | bool | This is the player's active tier |
| `is_affordable` | bool | Player has enough currency to reach this tier |
| `is_unlocked` | bool | Tier ≤ player's current tier (already purchased) |

**Frontend Usage:** Primary endpoint when entering the Black Market. Use `is_current` to highlight the active tier, `is_unlocked` to grey out already-purchased rows, and `is_affordable` to disable the upgrade button and show a "Not enough Gold" indicator.

---

### `POST /shop/upgrade/integrity`

Upgrades Core Capacity (Max Integrity) by one tier. Costs Gold.

**Request Body:**
```json
{ "player_id": "a1b2c3d4-..." }
```

**Success Response (200):**
```json
{
  "upgraded_to_tier": 4,
  "tier_details": {
    "tier": 4, "label": "Indomitable",
    "max_integrity_pct": 200, "cost_gold": 1500, "description": "..."
  },
  "gold_spent": 1500,
  "gold_remaining": 850,
  "profile_snapshot": {
    "gold": 850, "diamonds": 45,
    "integrity_level": 4, "velocity_level": 4,
    "freeze_spell_level": 2, "freeze_spells_held": 2
  }
}
```

**Frontend Usage:** Call on "Upgrade" button press for Core Integrity row. Use `profile_snapshot` to update the Gold counter and highlight the new active tier immediately without a full profile refresh.

---

### `POST /shop/upgrade/velocity`

Upgrades Kinetic Thrusters (Velocity) by one tier. Costs Gold.

**Request Body:**
```json
{ "player_id": "a1b2c3d4-..." }
```

**Success Response (200):** Same shape as `/shop/upgrade/integrity` with velocity-specific `tier_details`.

**Frontend Usage:** Same pattern as integrity upgrade. Tier label animations (e.g., "Dormant → Awakening") can be sourced from `tier_details.label`.

---

### `POST /shop/upgrade/freeze_spell`

Upgrades the Freezing Spell's mechanics by one tier. Costs Diamonds.  
Increasing tier extends freeze duration and reduces inventory weight (allowing more spells to be carried).

**Request Body:**
```json
{ "player_id": "a1b2c3d4-..." }
```

**Success Response (200):**
```json
{
  "upgraded_to_tier": 3,
  "tier_details": {
    "tier": 3, "label": "Cryo Pulse",
    "freeze_duration_seconds": 2.5,
    "inventory_weight_pct": 25,
    "cost_diamonds": 25, "description": "..."
  },
  "diamonds_spent": 25,
  "diamonds_remaining": 20,
  "max_spells_carriable": 4,
  "spells_held": 2,
  "profile_snapshot": { ... }
}
```

**Frontend Usage:** After upgrade, update:
- Diamond counter (use `diamonds_remaining`)
- Spell slot visualization: new `max_spells_carriable` determines how many slots to show
- If carrying spells compress (e.g., from 50% to 25% weight), show visual feedback that more slots opened up

---

### `POST /shop/buy/freeze_spell`

Purchases one consumable Freezing Spell unit using Gold.  
The per-unit Gold cost depends on the player's current spell tier.

**Request Body:**
```json
{ "player_id": "a1b2c3d4-..." }
```

**Success Response (200):**
```json
{
  "spells_held": 3,
  "max_spells_carriable": 4,
  "gold_spent": 180,
  "gold_remaining": 1070,
  "spell_tier": 3,
  "profile_snapshot": { ... }
}
```

**Error Case — Inventory Full (409):**
```json
{
  "ok": false,
  "error": {
    "code": "carry_limit_reached",
    "message": "Spell inventory is full. Current tier allows 4 spell(s). Upgrade your Freezing Spell level to carry more."
  }
}
```

**Frontend Usage:** Call when player taps the "Buy Spell" button in the Black Market. Update Gold counter, and visually fill one more spell slot in the inventory display. If `spells_held == max_spells_carriable`, grey out the buy button.

---

## Progression System Reference

### EXP → Level Formula

```
EXP required to reach level N = 300 × N^1.6
```

| Level | Cumulative EXP Required |
|-------|------------------------|
| 1 | 0 |
| 2 | 600 |
| 5 | 2,627 |
| 10 | 7,551 |
| 20 | 21,703 |
| 50 | 92,724 |

### Difficulty Float → Level Parameters

| Difficulty | Threat Rating | Grid Size | Bombs | Chasers | Chaser Interval |
|------------|---------------|-----------|-------|---------|-----------------|
| 0.00 | Stable | 10×10 | 0 | 0 | 30s |
| 0.25 | Perilous | 18×18 | 6 | 1 | 25s |
| 0.55 | Torment | 24×24 | 14 | 2 | 19s |
| 0.80 | Oblivion | 33×33 | 20 | 3 | 14s |
| 1.00 | Oblivion | 40×40 | 25 | 4 | 10s |

### Integrity Tier Effects

| Tier | Label | Max Integrity |
|------|-------|--------------|
| 0 | Standard | 100% |
| 1 | Reinforced | 125% |
| 2 | Fortified | 150% |
| 3 | Reinforced | 175% |
| 4 | Indomitable | 200% |

### Velocity Tier Speed Values

| Tier | Label | Speed Multiplier | Chaser Cap (×0.9) |
|------|-------|-----------------|-------------------|
| 0 | Dormant | 1.00× | 0.90× |
| 3 | Surging | 1.30× | 1.17× |
| 5 | Blazing | 1.55× | 1.40× |
| 8 | Thundering | 2.10× | 1.89× |
| 10 | Apex | 2.65× | 2.39× |

### Freeze Spell Tier Effects

| Tier | Label | Duration | Weight | Max Carry |
|------|-------|----------|--------|-----------|
| 1 | Glacial Shard | 1.5s | 50% | 2 |
| 2 | Frost Veil | 2.0s | 40% | 2 |
| 3 | Cryo Pulse | 2.5s | 25% | 4 |
| 4 | Arctic Wave | 3.5s | 20% | 5 |
| 5 | Void Blizzard | 5.0s | 20% | 5 |

---

## Recommended Frontend Flow

### App Launch
1. Check localStorage for `player_id`
2. If none → `POST /player/create` → store returned `player_id`
3. `GET /player/<id>` → hydrate Intro UI

### Entering Black Market
1. `GET /shop/player_state/<id>` → render all upgrade rows, spell inventory, currency counters

### Buying / Upgrading in Shop
1. User taps upgrade/buy button
2. Call appropriate endpoint (`/shop/upgrade/integrity`, etc.)
3. On success → update UI from `profile_snapshot` (no extra GET needed)
4. On error → display `error.message` to user

### Starting a Level
1. User taps "Begin Run" → transition to Loading UI
2. `POST /game/generate_level` with `player_id`
3. Animate 3-second countdown; display `maze.metadata` fields as they "stream in"
4. Dissolve into Gameplay Board; initialize grid from `maze.grid`, entities from `maze.loot` and `maze.hazards`
5. Initialize HUD from `player_snapshot`

### During Gameplay (Frontend-Only, no API calls)
- Player movement: step-and-hold on `maze.grid`
- Bomb trigger: BFS from player position; if any bomb within 3 path-steps → trigger
- Explosion: BFS flood-fill up to 5 tiles; blocked by `grid[r][c] == 1`
- Chaser pathfinding: A* or BFS on `maze.grid` from chaser positions toward player
- Chaser velocity cap: `velocity_multiplier × 0.9` from `player_snapshot`
- Freeze spell: pause all chaser movement and bomb timers for `freeze_duration_seconds`

### Path Reveal In-Game
1. User taps "Reveal Exit Path"
2. `POST /game/path_reveal_cost` → show Diamond cost in confirm modal
3. User confirms → `POST /game/purchase_path_reveal`
4. Frontend runs BFS/A* from player's current position to `maze.exit` → render golden trail
5. Start 5-second fade timer (`reveal_duration_seconds`)

### Level End
1. Win/loss detected client-side
2. `POST /game/complete_level` with all performance metrics
3. Display Game Result UI from `run_result`
4. On "Retreat to Courtyard" → `GET /player/<id>` to re-hydrate Intro UI

### Retry Level
1. User taps "Reconstruct Ruin (Retry)"
2. `POST /game/generate_level` with the original `seed` from the first generation
3. Identical maze is regenerated — player gets a fresh attempt at the same layout
