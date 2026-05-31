from __future__ import annotations

from flask import Blueprint, jsonify, request

from .admin_auth import require_admin_api_access
from .services.generation_admin_service import (
    AdminGenerationValidationError,
    cancel_admin_generation_job,
    cancel_admin_generation_job_batch,
    create_admin_generation_job,
    create_admin_generation_jobs_backfill,
    create_manual_generation_run,
    get_admin_generation_job_batch_status,
    get_admin_generation_job_detail,
    get_generation_coverage,
    get_generation_item_attempts,
    get_generation_run_detail,
    list_admin_generation_jobs,
    list_generation_runs,
    retry_admin_generation_job,
    retry_failed_admin_generation_job_batch,
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
        return _error_response(
            404,
            "generation_item_not_found",
            "Generation item not found.",
        )

    return jsonify(payload)


@bp.route("/generation/jobs/batches/<string:batch_id>/cancel", methods=["POST"])
def cancel_generation_job_batch_endpoint(batch_id: str):
    try:
        payload = cancel_admin_generation_job_batch(batch_id)
    except AdminGenerationValidationError as exc:
        return _error_response(400, "bad_admin_generation_request", str(exc))

    if payload is None:
        return _error_response(
            404,
            "generation_job_batch_not_found",
            "Generation job batch not found.",
        )

    return jsonify(payload)


@bp.route("/generation/jobs/batches/<string:batch_id>/retry-failed", methods=["POST"])
def retry_failed_generation_job_batch_endpoint(batch_id: str):
    try:
        payload = retry_failed_admin_generation_job_batch(batch_id)
    except AdminGenerationValidationError as exc:
        return _error_response(400, "bad_admin_generation_request", str(exc))

    if payload is None:
        return _error_response(
            404,
            "generation_job_batch_not_found",
            "Generation job batch not found.",
        )

    return jsonify(payload)


@bp.route("/generation/jobs", methods=["GET"])
def generation_jobs():
    try:
        return jsonify(list_admin_generation_jobs(request.args))
    except AdminGenerationValidationError as exc:
        return _error_response(400, "bad_admin_generation_request", str(exc))


@bp.route("/generation/jobs", methods=["POST"])
def create_generation_job():
    try:
        payload = create_admin_generation_job(_json_body())
    except AdminGenerationValidationError as exc:
        return _error_response(400, "bad_admin_generation_request", str(exc))

    return jsonify(payload)


@bp.route("/generation/jobs/backfill", methods=["POST"])
def create_generation_jobs_backfill():
    try:
        payload = create_admin_generation_jobs_backfill(_json_body())
    except AdminGenerationValidationError as exc:
        return _error_response(400, "bad_admin_generation_request", str(exc))

    return jsonify(payload)


@bp.route("/generation/jobs/batches/<string:batch_id>", methods=["GET"])
def generation_job_batch_status(batch_id: str):
    try:
        payload = get_admin_generation_job_batch_status(batch_id)
    except AdminGenerationValidationError as exc:
        return _error_response(400, "bad_admin_generation_request", str(exc))

    if payload is None:
        return _error_response(
            404,
            "generation_job_batch_not_found",
            "Generation job batch not found.",
        )

    return jsonify(payload)


@bp.route("/generation/jobs/<int:job_id>", methods=["GET"])
def generation_job_detail(job_id: int):
    try:
        payload = get_admin_generation_job_detail(job_id)
    except AdminGenerationValidationError as exc:
        return _error_response(400, "bad_admin_generation_request", str(exc))

    if payload is None:
        return _error_response(
            404,
            "generation_job_not_found",
            "Generation job not found.",
        )

    return jsonify(payload)


@bp.route("/generation/jobs/<int:job_id>/cancel", methods=["POST"])
def cancel_generation_job_endpoint(job_id: int):
    try:
        payload = cancel_admin_generation_job(job_id)
    except AdminGenerationValidationError as exc:
        return _error_response(400, "bad_admin_generation_request", str(exc))

    if payload is None:
        return _error_response(
            404,
            "generation_job_not_found",
            "Generation job not found.",
        )

    return jsonify(payload)


@bp.route("/generation/jobs/<int:job_id>/retry", methods=["POST"])
def retry_generation_job_endpoint(job_id: int):
    try:
        payload = retry_admin_generation_job(job_id)
    except AdminGenerationValidationError as exc:
        return _error_response(400, "bad_admin_generation_request", str(exc))

    if payload is None:
        return _error_response(
            404,
            "generation_job_not_found",
            "Generation job not found.",
        )

    return jsonify(payload)