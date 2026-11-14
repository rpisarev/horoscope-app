"""Additive database readiness endpoint, separate from public API liveness."""

from flask import Blueprint, jsonify

from . import db
from .services.readiness_service import database_ready


health_bp = Blueprint("health", __name__)


@health_bp.get("/health/ready")
def ready():
    # Reading the engine URL acquires no connection and cannot flush the session.
    is_ready = database_ready(db.engine.url)
    response = jsonify({"ready": is_ready})
    response.status_code = 200 if is_ready else 503
    response.headers["Cache-Control"] = "no-store"
    return response
