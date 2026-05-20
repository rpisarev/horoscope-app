from __future__ import annotations

from flask import Blueprint, jsonify, request

from .admin_auth import require_admin_api_access
from .services.generation_admin_service import (
    AdminGenerationValidationError,
    get_generation_coverage,
    get_generation_item_attempts,
    get_generation_run_detail,
    list_generation_runs,
)


bp = Blueprint("admin_api", __name__)


def _error_response(status_code: int, code: str, message: str):
    return jsonify({"error": {"code": code, "message": message}}), status_code


@bp.before_request
def _require_admin_access():
    return require_admin_api_access()


@bp.route("/generation/coverage")
def generation_coverage():
    try:
        return jsonify(get_generation_coverage(request.args))
    except AdminGenerationValidationError as exc:
        return _error_response(400, "bad_admin_generation_request", str(exc))


@bp.route("/generation/runs")
def generation_runs():
    try:
        return jsonify(list_generation_runs(request.args))
    except AdminGenerationValidationError as exc:
        return _error_response(400, "bad_admin_generation_request", str(exc))


@bp.route("/generation/runs/<int:run_id>")
def generation_run_detail(run_id: int):
    try:
        payload = get_generation_run_detail(run_id, request.args)
    except AdminGenerationValidationError as exc:
        return _error_response(400, "bad_admin_generation_request", str(exc))

    if payload is None:
        return _error_response(404, "generation_run_not_found", "Generation run not found.")

    return jsonify(payload)


@bp.route("/generation/items/<int:item_id>/attempts")
def generation_item_attempts(item_id: int):
    try:
        payload = get_generation_item_attempts(item_id, request.args)
    except AdminGenerationValidationError as exc:
        return _error_response(400, "bad_admin_generation_request", str(exc))

    if payload is None:
        return _error_response(404, "generation_item_not_found", "Generation item not found.")

    return jsonify(payload)