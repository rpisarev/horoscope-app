from __future__ import annotations

from flask import Blueprint, jsonify, request

from .admin_auth import require_admin_api_access
from .services.generation_admin_service import (
    AdminGenerationValidationError,
    create_manual_generation_run,
    get_generation_coverage,
    get_generation_item_attempts,
    get_generation_run_detail,
    list_generation_runs,
    retry_missing_generation,
)


bp = Blueprint("admin_api", __name__)


def _error_response(status_code: int, code: str, message: str):
    return jsonify({"error": {"code": code, "message": message}}), status_code


def _json_body() -> dict:
    payload = request.get_json(silent=True)
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise AdminGenerationValidationError("JSON body must be an object.")
    return payload


@bp.before_request
def _require_admin_access():
    return require_admin_api_access()


@bp.route("/generation/coverage", methods=["GET"])
def generation_coverage():
    try:
        return jsonify(get_generation_coverage(request.args))
    except AdminGenerationValidationError as exc:
        return _error_response(400, "bad_admin_generation_request", str(exc))


@bp.route("/generation/runs", methods=["GET"])
def generation_runs():
    try:
        return jsonify(list_generation_runs(request.args))
    except AdminGenerationValidationError as exc:
        return _error_response(400, "bad_admin_generation_request", str(exc))


@bp.route("/generation/runs", methods=["POST"])
def create_generation_run():
    try:
        payload = create_manual_generation_run(_json_body())
    except AdminGenerationValidationError as exc:
        return _error_response(400, "bad_admin_generation_request", str(exc))

    return jsonify(payload)


@bp.route("/generation/retry-missing", methods=["POST"])
def retry_missing_forecasts():
    try:
        payload = retry_missing_generation(_json_body())
    except AdminGenerationValidationError as exc:
        return _error_response(400, "bad_admin_generation_request", str(exc))

    return jsonify(payload)


@bp.route("/generation/runs/<int:run_id>", methods=["GET"])
def generation_run_detail(run_id: int):
    try:
        payload = get_generation_run_detail(run_id, request.args)
    except AdminGenerationValidationError as exc:
        return _error_response(400, "bad_admin_generation_request", str(exc))

    if payload is None:
        return _error_response(404, "generation_run_not_found", "Generation run not found.")

    return jsonify(payload)


@bp.route("/generation/items/<int:item_id>/attempts", methods=["GET"])
def generation_item_attempts(item_id: int):
    try:
        payload = get_generation_item_attempts(item_id, request.args)
    except AdminGenerationValidationError as exc:
        return _error_response(400, "bad_admin_generation_request", str(exc))

    if payload is None:
        return _error_response(404, "generation_item_not_found", "Generation item not found.")

    return jsonify(payload)