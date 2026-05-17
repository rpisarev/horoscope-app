from datetime import date, timedelta

import app.services.generation_service as generation_service

from app import db
from app.models import Forecast, GenerationAttempt, GenerationItem, GenerationRun
from app.providers import GenerationProviderError, ProviderResult
from app.services import SIGNS, save_forecast


class SuccessfulProvider:
    name = "test-success-provider"
    model_name = "test-success-model"

    def __init__(self):
        self.calls = 0

    def generate(self, request):
        self.calls += 1
        text = f"Generated forecast for {request.target_date.isoformat()} call {self.calls}"
        request_payload = request.to_payload()

        return ProviderResult(
            title="Generated title",
            text=text,
            payload={"call": self.calls},
            request_payload=request_payload,
            response_payload={"text": text},
            raw_response=text,
            provider=self.name,
            model_name=self.model_name,
        )


class RetryableFailureProvider:
    name = "test-retryable-provider"
    model_name = "test-retryable-model"

    def __init__(self):
        self.calls = 0

    def generate(self, request):
        self.calls += 1
        raise GenerationProviderError("Temporary provider failure", retryable=True)


def _install_provider(monkeypatch, provider):
    monkeypatch.setattr(
        generation_service,
        "get_horoscope_provider",
        lambda provider_name=None: provider,
    )


def test_run_daily_generation_creates_run_items_attempts_and_forecasts(app, monkeypatch):
    provider = SuccessfulProvider()
    _install_provider(monkeypatch, provider)

    target_day = date(2026, 5, 13)

    with app.app_context():
        run = generation_service.run_daily_generation(
            target_date=target_day,
            run_type="test",
            signs=["aries", "taurus"],
            provider_name="test",
            max_attempts=1,
        )

        db.session.refresh(run)

        assert run.status == "success"
        assert run.run_type == "test"
        assert run.target_date == target_day
        assert run.total_items == 2
        assert run.success_items == 2
        assert run.failed_items == 0
        assert run.skipped_items == 0
        assert run.finished_at is not None

        items = (
            GenerationItem.query.filter_by(run_id=run.id)
            .order_by(GenerationItem.sign_key)
            .all()
        )

        assert [item.sign_key for item in items] == ["aries", "taurus"]
        assert [item.status for item in items] == ["success", "success"]
        assert all(item.forecast_id for item in items)
        assert all(item.provider == provider.name for item in items)
        assert all(item.model_name == provider.model_name for item in items)

        attempts = (
            GenerationAttempt.query.join(GenerationItem)
            .filter(GenerationItem.run_id == run.id)
            .order_by(GenerationAttempt.id)
            .all()
        )

        assert len(attempts) == 2
        assert all(attempt.status == "success" for attempt in attempts)
        assert all(attempt.attempt_no == 1 for attempt in attempts)
        assert all(attempt.raw_response for attempt in attempts)

        forecasts = Forecast.query.order_by(Forecast.sign_key).all()

        assert [forecast.sign_key for forecast in forecasts] == ["aries", "taurus"]
        assert all(forecast.status == "published" for forecast in forecasts)
        assert all(forecast.source == provider.name for forecast in forecasts)
        assert all(forecast.model_name == provider.model_name for forecast in forecasts)
        assert all(forecast.generation_item_id is not None for forecast in forecasts)

        assert provider.calls == 2


def test_run_daily_generation_skips_existing_published_forecast(app, monkeypatch):
    provider = SuccessfulProvider()
    _install_provider(monkeypatch, provider)

    target_day = date(2026, 5, 13)

    with app.app_context():
        existing = save_forecast(
            sign="aries",
            day=target_day,
            text="Existing forecast text",
            model_version="existing-model",
            source="manual",
            status="published",
        )

        run = generation_service.run_daily_generation(
            target_date=target_day,
            run_type="test",
            signs=["aries"],
            provider_name="test",
            max_attempts=1,
        )

        db.session.refresh(run)

        assert run.status == "success"
        assert run.total_items == 1
        assert run.success_items == 0
        assert run.failed_items == 0
        assert run.skipped_items == 1

        item = GenerationItem.query.filter_by(run_id=run.id, sign_key="aries").one()

        assert item.status == "skipped"
        assert item.forecast_id == existing.id
        assert item.provider == "manual"
        assert item.model_name == "existing-model"
        assert item.finished_at is not None

        assert GenerationAttempt.query.count() == 0
        assert Forecast.query.count() == 1
        assert Forecast.query.one().text == "Existing forecast text"
        assert provider.calls == 0


def test_run_daily_generation_records_retryable_provider_failures(app, monkeypatch):
    provider = RetryableFailureProvider()
    _install_provider(monkeypatch, provider)

    target_day = date(2026, 5, 13)

    with app.app_context():
        run = generation_service.run_daily_generation(
            target_date=target_day,
            run_type="test",
            signs=["aries"],
            provider_name="test",
            max_attempts=2,
        )

        db.session.refresh(run)

        assert run.status == "failed"
        assert run.total_items == 1
        assert run.success_items == 0
        assert run.failed_items == 1
        assert run.skipped_items == 0
        assert run.finished_at is not None

        item = GenerationItem.query.filter_by(run_id=run.id, sign_key="aries").one()

        assert item.status == "failed"
        assert item.forecast_id is None
        assert item.error_message == "Temporary provider failure"

        attempts = GenerationAttempt.query.filter_by(item_id=item.id).order_by(
            GenerationAttempt.attempt_no
        ).all()

        assert len(attempts) == 2
        assert [attempt.attempt_no for attempt in attempts] == [1, 2]
        assert [attempt.status for attempt in attempts] == ["failed_retryable", "failed"]
        assert all(attempt.error_type == "GenerationProviderError" for attempt in attempts)
        assert all(attempt.error_message == "Temporary provider failure" for attempt in attempts)

        assert Forecast.query.count() == 0
        assert provider.calls == 2


def test_retry_for_missing_forecasts_generates_only_missing_signs(app, monkeypatch):
    provider = SuccessfulProvider()
    _install_provider(monkeypatch, provider)

    target_day = date(2026, 5, 13)
    missing_sign = "pisces"

    with app.app_context():
        for sign in SIGNS:
            if sign == missing_sign:
                continue

            save_forecast(
                sign=sign,
                day=target_day,
                text=f"Existing forecast for {sign}",
                model_version="existing-model",
                source="manual",
                status="published",
            )

        run = generation_service.run_retry_for_missing_forecasts(
            target_date=target_day,
            provider_name="test",
            max_attempts=1,
            max_retry_runs=3,
        )

        assert run is not None

        db.session.refresh(run)

        assert run.run_type == "retry"
        assert run.status == "success"
        assert run.total_items == 1
        assert run.success_items == 1
        assert run.failed_items == 0
        assert run.skipped_items == 0

        item = GenerationItem.query.filter_by(run_id=run.id).one()

        assert item.sign_key == missing_sign
        assert item.status == "success"
        assert item.forecast_id is not None

        assert provider.calls == 1
        assert Forecast.query.filter_by(target_date=target_day, status="published").count() == len(SIGNS)


def test_retry_for_missing_forecasts_returns_none_when_retry_limit_reached(app, monkeypatch):
    provider = SuccessfulProvider()
    _install_provider(monkeypatch, provider)

    target_day = date(2026, 5, 13)

    with app.app_context():
        retry_run = GenerationRun(
            run_type="retry",
            target_date=target_day,
            locale="ru",
            forecast_type="daily",
            status="success",
            total_items=0,
        )
        db.session.add(retry_run)
        db.session.commit()

        run = generation_service.run_retry_for_missing_forecasts(
            target_date=target_day,
            provider_name="test",
            max_attempts=1,
            max_retry_runs=1,
        )

        assert run is None
        assert provider.calls == 0


def test_generation_coverage_helpers_report_missing_and_complete_signs(app):
    target_day = date(2026, 5, 13)

    with app.app_context():
        assert generation_service.get_missing_forecast_signs(
            target_date=target_day,
            signs=["aries", "taurus"],
        ) == ["aries", "taurus"]

        assert (
            generation_service.has_generation_coverage(
                target_date=target_day,
                signs=["aries", "taurus"],
            )
            is False
        )

        save_forecast(
            sign="aries",
            day=target_day,
            text="Aries forecast",
            model_version="stub",
            source="stub",
            status="published",
        )

        assert generation_service.get_missing_forecast_signs(
            target_date=target_day,
            signs=["aries", "taurus"],
        ) == ["taurus"]

        save_forecast(
            sign="taurus",
            day=target_day,
            text="Taurus forecast",
            model_version="stub",
            source="stub",
            status="published",
        )

        assert generation_service.get_missing_forecast_signs(
            target_date=target_day,
            signs=["aries", "taurus"],
        ) == []

        assert (
            generation_service.has_generation_coverage(
                target_date=target_day,
                signs=["aries", "taurus"],
            )
            is True
        )


def test_close_stale_running_runs_marks_run_and_items_interrupted(app):
    target_day = date(2026, 5, 13)

    with app.app_context():
        run = GenerationRun(
            run_type="scheduled",
            target_date=target_day,
            locale="ru",
            forecast_type="daily",
            status="running",
            started_at=generation_service.utcnow() - timedelta(hours=3),
            total_items=1,
        )
        db.session.add(run)
        db.session.flush()

        item = GenerationItem(
            run_id=run.id,
            sign_key="aries",
            target_date=target_day,
            locale="ru",
            forecast_type="daily",
            status="pending",
        )
        db.session.add(item)
        db.session.commit()

        closed_count = generation_service.close_stale_running_runs(stale_after_hours=1)

        assert closed_count == 1

        db.session.refresh(run)
        db.session.refresh(item)

        assert run.status == "interrupted"
        assert run.finished_at is not None
        assert run.total_items == 1
        assert run.success_items == 0
        assert run.failed_items == 1
        assert run.skipped_items == 0
        assert "interrupted" in run.error_message

        assert item.status == "interrupted"
        assert item.finished_at is not None
        assert item.error_message == "Parent run was interrupted."