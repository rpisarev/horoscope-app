from datetime import date

from app.services.prompt_variation_service import (
    PROMPT_VARIATION_PROFILES,
    ZODIAC_SIGN_PROFILE_ORDER,
    build_prompt_variation_metadata,
    build_prompt_variation_variables,
    select_prompt_variation_profile,
)


def test_select_prompt_variation_profile_is_deterministic():
    first = select_prompt_variation_profile(
        sign_key="aries",
        target_date=date(2026, 5, 19),
        locale="ru",
        forecast_type="daily",
    )
    second = select_prompt_variation_profile(
        sign_key="aries",
        target_date=date(2026, 5, 19),
        locale="ru",
        forecast_type="daily",
    )

    assert first == second


def test_known_daily_signs_use_all_profiles_for_same_date():
    selected_keys = {
        select_prompt_variation_profile(
            sign_key=sign_key,
            target_date=date(2026, 5, 19),
            locale="ru",
            forecast_type="daily",
        ).key
        for sign_key in ZODIAC_SIGN_PROFILE_ORDER
    }

    assert len(selected_keys) == len(PROMPT_VARIATION_PROFILES)


def test_prompt_variation_variables_do_not_expose_sign_or_date():
    variables = build_prompt_variation_variables(
        sign_key="aries",
        target_date=date(2026, 5, 19),
        locale="ru",
        forecast_type="daily",
    )

    serialized_variables = "\n".join(str(value) for value in variables.values()).lower()

    assert "aries" not in serialized_variables
    assert "2026-05-19" not in serialized_variables
    assert "prompt_variation_key" in variables
    assert "prompt_variation_theme" in variables
    assert "prompt_variation_mood" in variables
    assert "prompt_variation_tone" in variables
    assert "prompt_variation_avoid" in variables


def test_prompt_variation_metadata_keeps_internal_seed_and_profile():
    metadata = build_prompt_variation_metadata(
        sign_key="aries",
        target_date=date(2026, 5, 19),
        locale="ru",
        forecast_type="daily",
    )

    assert metadata["profile"]["key"]
    assert metadata["seed"] == "aries:2026-05-19:ru:daily:prompt-variation-v1"