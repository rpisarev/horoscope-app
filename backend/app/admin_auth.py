from __future__ import annotations

import hmac
from typing import Any

from flask import current_app, jsonify, request
from werkzeug.wrappers import Response


TRUE_VALUES = {"1", "true", "yes", "on"}


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in TRUE_VALUES


def _error_response(status_code: int, code: str, message: str) -> tuple[Response, int]:
    return jsonify({"error": {"code": code, "message": message}}), status_code


def require_admin_api_access() -> tuple[Response, int] | None:
    if not _as_bool(current_app.config.get("ADMIN_API_ENABLED")):
        return _error_response(
            404,
            "admin_api_disabled",
            "Admin API is disabled.",
        )

    expected_token = current_app.config.get("ADMIN_API_TOKEN")
    if not expected_token:
        return _error_response(
            500,
            "admin_api_misconfigured",
            "Admin API token is not configured.",
        )

    auth_header = request.headers.get("Authorization", "")
    scheme, _, provided_token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not provided_token:
        return _error_response(
            401,
            "admin_token_required",
            "Admin API requires Authorization: Bearer <token>.",
        )

    if not hmac.compare_digest(str(expected_token), provided_token):
        return _error_response(
            403,
            "admin_token_invalid",
            "Admin API token is invalid.",
        )

    return None