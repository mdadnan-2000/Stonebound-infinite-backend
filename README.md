# Stonebound: Infinite — Backend

Python/Flask RESTful backend for the procedurally generated arcade maze game.

## Setup

```bash
pip install -r requirements.txt
python app.py
```

Server runs on `http://localhost:5000` by default.

## Project Structure

```
stonebound_backend/
├── app.py                    # Flask app factory & entry point
├── requirements.txt
├── API_REFERENCE.md          # Complete API documentation
│
├── core/                     # Game logic (no Flask dependencies)
│   ├── progression.py        # EXP → level → difficulty mapping
│   ├── maze_engine.py        # Procedural maze generation
│   ├── exp_engine.py         # Performance-based EXP calculation
│   └── shop_matrix.py        # Black Market Matrix (authoritative pricing)
│
├── api/                      # Flask route blueprints
│   ├── player_routes.py      # /player/* endpoints
│   ├── game_routes.py        # /game/* endpoints
│   └── shop_routes.py        # /shop/* endpoints
│
├── utils/                    # Shared utilities
│   ├── persistence.py        # JSON file read/write (profiles.json)
│   └── helpers.py            # Response builders, validators
│
└── data/
    └── profiles.json         # Auto-created on first run
```

## Environment Variables

| Variable | Default | Notes |
|----------|---------|-------|
| `FLASK_SECRET_KEY` | `stonebound-dev-secret-...` | **Change in production** |
| `FLASK_DEBUG` | `1` | Set to `0` in production |
| `FLASK_HOST` | `0.0.0.0` | Bind host |
| `FLASK_PORT` | `5000` | Bind port |

## Key Design Decisions

- **Backend-authoritative shop:** All item costs live in `core/shop_matrix.py`. The frontend never defines prices.
- **Infinite progression:** EXP → difficulty via log curve; no per-level config needed.
- **Hybrid pathfinding:** Backend generates the static grid and spawn coordinates. The frontend handles all real-time entity movement.
- **JSON persistence:** `data/profiles.json` written atomically (temp file + rename) to prevent corruption.
- **Deterministic mazes:** Pass a `seed` to `/game/generate_level` to regenerate the same maze for retries.
