"""Authentication — /api/auth.

JWT bearer tokens: identity is str(user.id) with a `role` claim so the
frontend can gate UI without a second round-trip.

Response shape is {"access_token", "user"}. The map-dashboard-starter
template returned {"token", "user"} while its own frontend read
`res.access_token`, so the token was never stored and every protected call
401'd. Both sides are standardised on `access_token` here.
"""
from __future__ import annotations

from functools import wraps

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required

from .errors import api_error
from .models import User, db

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

DEMO_ROLE = "admin"


# --- seeding -----------------------------------------------------------------

def seed_admin_user() -> None:
    """Create the bootstrap admin if no users exist yet (idempotent)."""
    username = current_app.config["ADMIN_USERNAME"]
    if User.query.filter_by(username=username).first():
        return
    user = User(
        username=username,
        email=current_app.config["ADMIN_EMAIL"],
        role="admin",
    )
    user.set_password(current_app.config["ADMIN_PASSWORD"])
    db.session.add(user)
    db.session.commit()
    print(f"[auth] seeded admin user '{username}'", flush=True)


# --- helpers -----------------------------------------------------------------

def _synthetic_demo_user(username: str) -> dict:
    return {
        "id": 0,
        "username": username or current_app.config["ADMIN_USERNAME"],
        "email": None,
        "role": DEMO_ROLE,
        "is_active": True,
        "created_at": None,
    }


def _issue_token(user_id, role: str) -> str:
    return create_access_token(identity=str(user_id), additional_claims={"role": role})


def current_user() -> User | None:
    """Resolve the JWT identity to a User row, or None in demo mode."""
    uid = get_jwt_identity()
    if uid is None:
        return None
    try:
        return db.session.get(User, int(uid))
    except (TypeError, ValueError):
        return None


def admin_required(fn):
    """Guard for admin-only routes. Applied *inside* @jwt_required()."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if current_app.config["DEMO_MODE"] and user is None:
            return fn(*args, **kwargs)
        if user is None or not user.is_admin:
            body, status = api_error("permission_denied", 403)
            return jsonify(body), status
        return fn(*args, **kwargs)
    return wrapper


# --- routes ------------------------------------------------------------------

@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if current_app.config["DEMO_MODE"]:
        demo = _synthetic_demo_user(username)
        return jsonify({"access_token": _issue_token(demo["id"], demo["role"]), "user": demo}), 200

    if not username or not password:
        body, status = api_error("invalid_request", 400, "Username and password are required.")
        return jsonify(body), status

    user = (
        User.query.filter_by(username=username).first()
        or User.query.filter_by(email=username).first()
    )
    if not user or not user.check_password(password):
        body, status = api_error("invalid_request", 401, "Invalid username or password.")
        return jsonify(body), status
    if not user.is_active:
        body, status = api_error("permission_denied", 403, "This account is deactivated.")
        return jsonify(body), status

    return jsonify({
        "access_token": _issue_token(user.id, user.role),
        "user": user.to_dict(),
    }), 200


@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    uid = get_jwt_identity()
    if current_app.config["DEMO_MODE"] and str(uid) == "0":
        return jsonify(_synthetic_demo_user(current_app.config["ADMIN_USERNAME"])), 200

    user = current_user()
    if not user:
        body, status = api_error("not_found", 404, "User not found.")
        return jsonify(body), status
    return jsonify(user.to_dict()), 200


@auth_bp.route("/logout", methods=["POST"])
def logout():
    """Stateless logout — the client drops the token."""
    return jsonify({"ok": True}), 200
