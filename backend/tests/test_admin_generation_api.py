from datetime import date

import pytest

from app import db
from app.models import GenerationAttempt, GenerationItem, GenerationRun
from app.services import SIGNS, save_forecast


ADMIN_TOKEN = "test-admin-token"


@pytest.fixture(autouse=True)
def reset_admin_api_config(app):
    app.config.update(
        ADMIN_API_ENABLED=False,
        ADMIN_API_TOKEN=None,
        ADMIN_API_ALLOW_OPENAI=False,
    )
    yield
    app.config.update(
        ADMIN_API_ENABLED=False,
        ADMIN_API_TOKEN=None,
        ADMIN_API_ALLOW_OPENAI=False,
    )


def _enable_admin_api(app, *, token: str = ADMIN_TOKEN) -> None:
    app.config.update(
        ADMIN_API_ENABLED=True,
        ADMIN_API_TOKEN=token,
    )


def _admin_headers(token: str = ADMIN_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_admin_api_is_disabled_by_default(client):
    response = client.get(
        "/api/admin/generation/runs",
        headers=_admin_headers(),
    )

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "admin_api_disabled"


def test_admin_api_requires_bearer_token(app, client):
    _enable_admin_api(app)

    response = client.get("/api/admin/generation/runs")

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "admin_token_required"


def test_admin_api_rejects_wrong_token(app, client):
    _enable_admin_api(app)

    response = client.get(
        "/api/admin/generation/runs",
        headers=_admin_headers("wrong-token"),
    )

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "admin_token_invalid"


def test_admin_api_reports_missing_token_configuration(app, client):
    app.config.update(
        ADMIN_API_ENABLED=True,
        ADMIN_API_TOKEN=None,
    )

    response = client.get(
        "/api/admin/generation/runs",
        headers=_admin_headers(),
    )

    assert response.status_code == 500
    assert response.get_json()["error"]["code"] == "admin_api_misconfigured"


def test_generation_coverage_reports_published_and_missing_signs(app, client):
    _enable_admin_api(app)
    target_day = date(2026, 6, 6)

    with app.app_context():
        save_forecast(
            sign="aries",
            day=target_day,
            text="Existing published forecast.",
            model_version="stub",
            source="stub",
            status="published",
        )

    response = client.get(
        f"/api/admin/generation/coverage?date={target_day.isoformat()}",
        headers=_admin_headers(),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["date"] == target_day.isoformat()
    assert payload["locale"] == "ru"
    assert payload["forecast_type"] == "daily"
    assert payload["total_signs"] == len(SIGNS)
    assert payload["published_count"] == 1
    assert payload["missing_count"] == len(SIGNS) - 1
    assert payload["has_coverage"] is False
    assert "aries" in payload["published_signs"]
    assert "aries" not in payload["missing_signs"]


def test_generation_coverage_requires_valid_date(app, client):
    _enable_admin_api(app)

    response = client.get(
        "/api/admin/generation/coverage?date=bad-date",
        headers=_admin_headers(),
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "bad_admin_generation_request"


def test_list_generation_runs_returns_summaries(app, client):
    _enable_admin_api(app)
    target_day = date(2026, 6, 6)

    with app.app_context():
        run = GenerationRun(
            run_type="manual",
            target_date=target_day,
            locale="ru",
            forecast_type="daily",
            status="partial_failed",
            total_items=2,
            success_items=1,
            failed_items=1,
            skipped_items=0,
        )
        db.session.add(run)
        db.session.commit()

    response = client.get(
        f"/api/admin/generation/runs?date={target_day.isoformat()}&status=partial_failed",
        headers=_admin_headers(),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["total_count"] == 1
    assert payload["limit"] == 20
    assert payload["offset"] == 0
    assert len(payload["items"]) == 1
    assert payload["items"][0]["run_type"] == "manual"
    assert payload["items"][0]["status"] == "partial_failed"
    assert payload["items"][0]["date"] == target_day.isoformat()


def test_generation_run_detail_returns_items_without_payloads_by_default(app, client):
    _enable_admin_api(app)
    target_day = date(2026, 6, 6)

    with app.app_context():
        run = GenerationRun(
            run_type="manual",
            target_date=target_day,
            locale="ru",
            forecast_type="daily",
            status="success",
            total_items=1,
            success_items=1,
            failed_items=0,
            skipped_items=0,
        )
        db.session.add(run)
        db.session.flush()
        item = GenerationItem(
            run_id=run.id,
            sign_key="aries",
            target_date=target_day,
            locale="ru",
            forecast_type="daily",
            status="success",
            provider="stub",
            model_name="stub-model",
            request_payload={"secret_safe": True},
            response_payload={"ok": True},
            raw_response="raw text",
        )
        db.session.add(item)
        db.session.commit()
        run_id = run.id

    response = client.get(
        f"/api/admin/generation/runs/{run_id}",
        headers=_admin_headers(),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["id"] == run_id
    assert len(payload["items"]) == 1
    assert payload["items"][0]["sign_key"] == "aries"
    assert "request_payload" not in payload["items"][0]
    assert "response_payload" not in payload["items"][0]
    assert "raw_response" not in payload["items"][0]


def test_generation_run_detail_can_include_payloads(app, client):
    _enable_admin_api(app)
    target_day = date(2026, 6, 6)

    with app.app_context():
        run = GenerationRun(
            run_type="manual",
            target_date=target_day,
            locale="ru",
            forecast_type="daily",
            status="success",
            total_items=1,
            success_items=1,
            failed_items=0,
            skipped_items=0,
        )
        db.session.add(run)
        db.session.flush()
        item = GenerationItem(
            run_id=run.id,
            sign_key="aries",
            target_date=target_day,
            locale="ru",
            forecast_type="daily",
            status="success",
            request_payload={"prompt": "safe"},
            response_payload={"text": "ok"},
            raw_response="raw text",
        )
        db.session.add(item)
        db.session.commit()
        run_id = run.id

    response = client.get(
        f"/api/admin/generation/runs/{run_id}?include_payloads=1",
        headers=_admin_headers(),
    )

    assert response.status_code == 200
    item_payload = response.get_json()["items"][0]
    assert item_payload["request_payload"] == {"prompt": "safe"}
    assert item_payload["response_payload"] == {"text": "ok"}
    assert item_payload["raw_response"] == "raw text"


def test_generation_item_attempts_returns_attempts_without_payloads_by_default(app, client):
    _enable_admin_api(app)
    target_day = date(2026, 6, 6)

    with app.app_context():
        run = GenerationRun(
            run_type="manual",
            target_date=target_day,
            locale="ru",
            forecast_type="daily",
            status="failed",
            total_items=1,
            success_items=0,
            failed_items=1,
            skipped_items=0,
        )
        db.session.add(run)
        db.session.flush()
        item = GenerationItem(
            run_id=run.id,
            sign_key="aries",
            target_date=target_day,
            locale="ru",
            forecast_type="daily",
            status="failed",
            provider="stub",
            model_name="stub-model",
        )
        db.session.add(item)
        db.session.flush()
        attempt = GenerationAttempt(
            item_id=item.id,
            attempt_no=1,
            status="failed",
            provider="stub",
            model_name="stub-model",
            request_payload={"prompt": "safe"},
            response_payload={"error": "nope"},
            raw_response="raw failed text",
            error_type="GenerationProviderError",
            error_message="Provider failed.",
        )
        db.session.add(attempt)
        db.session.commit()
        item_id = item.id

    response = client.get(
        f"/api/admin/generation/items/{item_id}/attempts",
        headers=_admin_headers(),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["item"]["id"] == item_id
    assert len(payload["attempts"]) == 1
    assert payload["attempts"][0]["attempt_no"] == 1
    assert payload["attempts"][0]["status"] == "failed"
    assert payload["attempts"][0]["error_type"] == "GenerationProviderError"
    assert "request_payload" not in payload["attempts"][0]
    assert "response_payload" not in payload["attempts"][0]
    assert "raw_response" not in payload["attempts"][0]


def test_generation_detail_endpoints_return_404_for_unknown_ids(app, client):
    _enable_admin_api(app)

    run_response = client.get(
        "/api/admin/generation/runs/999999",
        headers=_admin_headers(),
    )
    item_response = client.get(
        "/api/admin/generation/items/999999/attempts",
        headers=_admin_headers(),
    )

    assert run_response.status_code == 404
    assert run_response.get_json()["error"]["code"] == "generation_run_not_found"
    assert item_response.status_code == 404
    assert item_response.get_json()["error"]["code"] == "generation_item_not_found"