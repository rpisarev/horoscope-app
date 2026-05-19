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


def test_known_daily_signs_use_maximum_available_profile_spread_for_same_date():
    selected_profile_keys = [
        select_prompt_variation_profile(
            sign_key=sign_key,
            target_date=date(2026, 5, 19),
            locale="ru",
            forecast_type="daily",
        ).key
        for sign_key in ZODIAC_SIGN_PROFILE_ORDER
    ]

    unique_selected_profile_keys = set(selected_profile_keys)
    available_profile_keys = {profile.key for profile in PROMPT_VARIATION_PROFILES}

    assert unique_selected_profile_keys <= available_profile_keys
    assert len(unique_selected_profile_keys) == min(
        len(ZODIAC_SIGN_PROFILE_ORDER),
        len(PROMPT_VARIATION_PROFILES),
    )


def test_known_daily_sign_profile_rotation_changes_between_dates():
    first_day_profile_keys = [
        select_prompt_variation_profile(
            sign_key=sign_key,
            target_date=date(2026, 5, 19),
            locale="ru",
            forecast_type="daily",
        ).key
        for sign_key in ZODIAC_SIGN_PROFILE_ORDER
    ]
    second_day_profile_keys = [
        select_prompt_variation_profile(
            sign_key=sign_key,
            target_date=date(2026, 5, 20),
            locale="ru",
            forecast_type="daily",
        ).key
        for sign_key in ZODIAC_SIGN_PROFILE_ORDER
    ]

    assert first_day_profile_keys != second_day_profile_keys


def test_unknown_sign_profile_selection_is_stable_and_valid():
    profile = select_prompt_variation_profile(
        sign_key="unknown-sign",
        target_date=date(2026, 5, 19),
        locale="ru",
        forecast_type="daily",
    )
    second_profile = select_prompt_variation_profile(
        sign_key="unknown-sign",
        target_date=date(2026, 5, 19),
        locale="ru",
        forecast_type="daily",
    )

    available_profile_keys = {item.key for item in PROMPT_VARIATION_PROFILES}

    assert profile == second_profile
    assert profile.key in available_profile_keys


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
    assert "prompt_variation_composition" in variables
    assert "prompt_variation_opening_move" in variables
    assert "prompt_variation_concrete_zone" in variables
    assert "prompt_variation_ending_energy" in variables
    assert "prompt_variation_sentence_style" in variables
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