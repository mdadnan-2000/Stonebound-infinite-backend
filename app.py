"""
app.py
=======
Flask application factory and entry point for Stonebound: Infinite backend.

WHY APPLICATION FACTORY PATTERN:
Creating the app inside a function (rather than at module level) allows:
  1. Easy testing — instantiate fresh apps per test
  2. Multiple configs (dev/prod) without code changes
  3. Blueprint registration is explicit and inspectable

RUNNING:
  python app.py            (development server, debug mode)
  flask run                (production-ready via gunicorn or similar)

ENVIRONMENT VARIABLES:
  FLASK_SECRET_KEY    — Secret key for session signing (set in production!)
  FLASK_DEBUG         — Set to "1" for debug mode (never in production)
  FLASK_HOST          — Bind host (default: 0.0.0.0)
  FLASK_PORT          — Bind port (default: 5000)
"""

import os
from flask import Flask, jsonify
from flask_cors import CORS

from api.player_routes import player_bp
from api.game_routes import game_bp
from api.shop_routes import shop_bp


def create_app() -> Flask:
    """
    Creates and configures the Flask application.

    Blueprint registration order matters for URL conflict resolution —
    more specific routes should be registered before general ones.
    """
    app = Flask(__name__)

    # ── SECRET KEY ─────────────────────────────────────────────────────────
    # Used for session signing. MUST be changed to a real secret in production.
    app.config["SECRET_KEY"] = os.environ.get(
        "FLASK_SECRET_KEY", "stonebound-dev-secret-change-in-production"
    )

    # ── CORS CONFIGURATION ─────────────────────────────────────────────────
    # Allow requests from any origin in development.
    # In production, restrict to your game's domain:
    #   CORS(app, resources={r"/*": {"origins": "https://yourgame.com"}})
    CORS(app)

    # ── REGISTER BLUEPRINTS ────────────────────────────────────────────────
    app.register_blueprint(player_bp)
    app.register_blueprint(game_bp)
    app.register_blueprint(shop_bp)

    # ── GLOBAL ERROR HANDLERS ─────────────────────────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({
            "ok": False,
            "data": None,
            "error": {"code": "not_found", "message": "The requested endpoint does not exist."}
        }), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({
            "ok": False,
            "data": None,
            "error": {"code": "method_not_allowed", "message": "HTTP method not allowed for this endpoint."}
        }), 405

    @app.errorhandler(500)
    def internal_error(e):
        return jsonify({
            "ok": False,
            "data": None,
            "error": {"code": "internal_error", "message": "An unexpected server error occurred."}
        }), 500

    # ── HEALTH CHECK ENDPOINT ─────────────────────────────────────────────
    @app.route("/health", methods=["GET"])
    def health():
        """
        GET /health
        Simple liveness check. Returns 200 if the server is running.
        Used by deployment tooling and monitoring systems.
        """
        return jsonify({"ok": True, "service": "Stonebound: Infinite API", "version": "1.0.0"})

    # ── ROOT INFO ENDPOINT ────────────────────────────────────────────────
    @app.route("/", methods=["GET"])
    def index():
        """Lists all registered routes for quick developer reference."""
        routes = []
        for rule in app.url_map.iter_rules():
            routes.append({
                "endpoint": rule.endpoint,
                "methods": sorted([m for m in rule.methods if m not in ("HEAD", "OPTIONS")]),
                "url": str(rule),
            })
        return jsonify({
            "ok": True,
            "service": "Stonebound: Infinite — Backend API",
            "routes": sorted(routes, key=lambda r: r["url"]),
        })

    return app


# ── ENTRYPOINT ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = create_app()
    host = os.environ.get("FLASK_HOST", "0.0.0.0")
    port = int(os.environ.get("FLASK_PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"

    print(f"\n🪨  Stonebound: Infinite — Backend API")
    print(f"   Running on http://{host}:{port}")
    print(f"   Debug mode: {'ON' if debug else 'OFF'}\n")

    app.run(host=host, port=port, debug=debug)
