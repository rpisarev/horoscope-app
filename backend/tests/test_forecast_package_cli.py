import pytest

from utils import generate_forecast_package as cli


@pytest.fixture
def cli_calls(app, monkeypatch):
    """Exercise real argument/gate handling without executing generation."""
    calls = []

    def record_generation(**kwargs):
        calls.append(kwargs)
        return object()

    monkeypatch.setenv("HOROSCOPE_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-never-used")
    monkeypatch.setitem(app.config, "APP_DEPLOYMENT_MODE", "development")
    monkeypatch.setattr(cli, "load_local_env", lambda: None)
    monkeypatch.setattr("app.create_app", lambda: app)
    monkeypatch.setattr("app.services.run_daily_generation", record_generation)
    monkeypatch.setattr(cli, "print_run_summary", lambda run: None)
    return calls


def set_args(monkeypatch, *args):
    monkeypatch.setattr(
        "sys.argv",
        ["generate_forecast_package.py", "--date", "2026-09-28", *args],
    )


@pytest.mark.parametrize("provider", ["", " \t\n "])
def test_explicit_blank_provider_rejected_before_gates_or_generation(
    monkeypatch, cli_calls, provider,
):
    def unexpected_gate(*args, **kwargs):
        pytest.fail("Blank provider must be rejected before OpenAI checks")

    monkeypatch.setattr(cli, "require_openai_safety_confirmation", unexpected_gate)
    monkeypatch.setattr(cli, "require_openai_key_if_needed", unexpected_gate)
    set_args(monkeypatch, "--provider", provider)

    with pytest.raises(SystemExit, match="--provider must not be empty or whitespace-only"):
        cli.main()

    # Even with HOROSCOPE_PROVIDER=openai and a key, nothing reaches lifecycle
    # or its factory fallback.
    assert cli_calls == []


@pytest.mark.parametrize("provider_args", [[], ["--provider", "openai"]])
def test_omitted_or_explicit_openai_still_requires_opt_in(monkeypatch, cli_calls, provider_args):
    set_args(monkeypatch, *provider_args)

    with pytest.raises(SystemExit, match="without --allow-openai"):
        cli.main()

    assert cli_calls == []


@pytest.mark.parametrize("provider_args", [[], ["--provider", "openai"]])
def test_omitted_or_explicit_openai_is_forwarded_after_opt_in(monkeypatch, cli_calls, provider_args):
    # Omission retains the CLI's OpenAI default, independently of environment.
    monkeypatch.setenv("HOROSCOPE_PROVIDER", "stub")
    set_args(monkeypatch, *provider_args, "--allow-openai")

    cli.main()

    assert len(cli_calls) == 1
    assert cli_calls[0]["provider_name"] == "openai"


def test_openai_opt_in_still_requires_key(monkeypatch, cli_calls):
    monkeypatch.delenv("OPENAI_API_KEY")
    set_args(monkeypatch, "--provider", "openai", "--allow-openai")

    with pytest.raises(SystemExit, match="OPENAI_API_KEY is missing"):
        cli.main()

    assert cli_calls == []


def test_explicit_stub_does_not_inherit_openai_environment(monkeypatch, cli_calls):
    monkeypatch.delenv("OPENAI_API_KEY")
    set_args(monkeypatch, "--provider", " STUB ")

    cli.main()

    assert len(cli_calls) == 1
    assert cli_calls[0]["provider_name"] == "stub"
