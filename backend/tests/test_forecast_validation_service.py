import pytest

from app.services.forecast_validation_service import (
    find_forbidden_forecast_terms,
    has_forbidden_forecast_terms,
)


def test_find_forbidden_forecast_terms_accepts_personal_address_text():
    text = (
        "Вас ждет спокойный день с возможностью сосредоточиться на главном. "
        "Вам будет проще договориться о важном, если говорить мягко и ясно."
    )

    assert find_forbidden_forecast_terms(text, locale="ru") == []
    assert has_forbidden_forecast_terms(text, locale="ru") is False


@pytest.mark.parametrize(
    "text,term",
    [
        ("Овнов сегодня ждет удача.", "овнов"),
        ("Тельцам стоит быть внимательнее.", "тельцам"),
        ("Близнецы могут получить приятную новость.", "близнецы"),
        ("Для Козерогов день будет насыщенным.", "козерогов"),
        ("Рыбам важно не спешить.", "рыбам"),
        ("Змееносцам стоит прислушаться к себе.", "змееносцам"),
    ],
)
def test_find_forbidden_forecast_terms_detects_zodiac_sign_names(text, term):
    violations = find_forbidden_forecast_terms(text, locale="ru")

    assert violations
    assert any(violation.code == "zodiac_sign_name" for violation in violations)
    assert any(violation.term == term for violation in violations)
    assert has_forbidden_forecast_terms(text, locale="ru") is True


@pytest.mark.parametrize(
    "text,term",
    [
        ("Представители знака почувствуют прилив сил.", "представители знака"),
        ("Для вашего знака это хороший момент для отдыха.", "для вашего знака"),
        ("Ваш знак может получить важный совет.", "ваш знак"),
        ("Люди этого знака будут особенно убедительны.", "люди этого знака"),
    ],
)
def test_find_forbidden_forecast_terms_detects_generic_zodiac_phrases(text, term):
    violations = find_forbidden_forecast_terms(text, locale="ru")

    assert violations
    assert any(violation.code == "zodiac_sign_phrase" for violation in violations)
    assert any(violation.term == term for violation in violations)


def test_find_forbidden_forecast_terms_ignores_unsupported_locale_for_now():
    assert find_forbidden_forecast_terms("Aries will be lucky.", locale="en") == []