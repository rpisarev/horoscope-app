from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ForecastTextViolation:
    code: str
    term: str
    message: str


_RU_WORD_BOUNDARY_LEFT = r"(?<![А-Яа-яЁё])"
_RU_WORD_BOUNDARY_RIGHT = r"(?![А-Яа-яЁё])"

_FORBIDDEN_RU_SIGN_TERMS = [
    "овен",
    "овна",
    "овну",
    "овном",
    "овне",
    "овны",
    "овнов",
    "овнам",
    "овнами",
    "овнах",
    "телец",
    "тельца",
    "тельцу",
    "тельцом",
    "тельце",
    "тельцы",
    "тельцов",
    "тельцам",
    "тельцами",
    "тельцах",
    "близнецы",
    "близнецов",
    "близнецам",
    "близнецами",
    "близнецах",
    "рак",
    "рака",
    "раку",
    "раком",
    "раке",
    "раки",
    "раков",
    "ракам",
    "раками",
    "раках",
    "лев",
    "льва",
    "льву",
    "львом",
    "льве",
    "львы",
    "львов",
    "львам",
    "львами",
    "львах",
    "дева",
    "девы",
    "деве",
    "деву",
    "девой",
    "девою",
    "дев",
    "девам",
    "девами",
    "девах",
    "весы",
    "весов",
    "весам",
    "весами",
    "весах",
    "скорпион",
    "скорпиона",
    "скорпиону",
    "скорпионом",
    "скорпионе",
    "скорпионы",
    "скорпионов",
    "скорпионам",
    "скорпионами",
    "скорпионах",
    "стрелец",
    "стрельца",
    "стрельцу",
    "стрельцом",
    "стрельце",
    "стрельцы",
    "стрельцов",
    "стрельцам",
    "стрельцами",
    "стрельцах",
    "козерог",
    "козерога",
    "козерогу",
    "козерогом",
    "козероге",
    "козероги",
    "козерогов",
    "козерогам",
    "козерогами",
    "козерогах",
    "водолей",
    "водолея",
    "водолею",
    "водолеем",
    "водолее",
    "водолеи",
    "водолеев",
    "водолеям",
    "водолеями",
    "водолеях",
    "рыбы",
    "рыб",
    "рыбам",
    "рыбами",
    "рыбах",
    "змееносец",
    "змееносца",
    "змееносцу",
    "змееносцем",
    "змееносце",
    "змееносцы",
    "змееносцев",
    "змееносцам",
    "змееносцами",
    "змееносцах",
]

_FORBIDDEN_RU_PHRASES = [
    "знак зодиака",
    "знака зодиака",
    "знаку зодиака",
    "представители знака",
    "представителям знака",
    "представителей знака",
    "люди этого знака",
    "людям этого знака",
    "для этого знака",
    "для вашего знака",
    "ваш знак",
    "вашего знака",
    "вашему знаку",
]


def find_forbidden_forecast_terms(
    text: str | None,
    *,
    locale: str = "ru",
) -> list[ForecastTextViolation]:
    if not text or locale != "ru":
        return []

    violations: list[ForecastTextViolation] = []
    seen: set[tuple[str, str]] = set()

    for term in _FORBIDDEN_RU_SIGN_TERMS:
        pattern = _word_pattern(term)
        if re.search(pattern, text, flags=re.IGNORECASE):
            _append_violation(
                violations,
                seen,
                code="zodiac_sign_name",
                term=term,
                message="Forecast text must not mention zodiac sign names.",
            )

    for phrase in _FORBIDDEN_RU_PHRASES:
        pattern = re.escape(phrase).replace(r"\ ", r"\s+")
        if re.search(pattern, text, flags=re.IGNORECASE):
            _append_violation(
                violations,
                seen,
                code="zodiac_sign_phrase",
                term=phrase,
                message="Forecast text must not use generic zodiac sign phrases.",
            )

    return violations


def has_forbidden_forecast_terms(text: str | None, *, locale: str = "ru") -> bool:
    return bool(find_forbidden_forecast_terms(text, locale=locale))


def _word_pattern(term: str) -> str:
    return f"{_RU_WORD_BOUNDARY_LEFT}{re.escape(term)}{_RU_WORD_BOUNDARY_RIGHT}"


def _append_violation(
    violations: list[ForecastTextViolation],
    seen: set[tuple[str, str]],
    *,
    code: str,
    term: str,
    message: str,
) -> None:
    key = (code, term)
    if key in seen:
        return

    seen.add(key)
    violations.append(
        ForecastTextViolation(
            code=code,
            term=term,
            message=message,
        )
    )