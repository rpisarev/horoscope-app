from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


DEFAULT_LOCALE = "ru"
DEFAULT_FORECAST_TYPE = "daily"
DEFAULT_STATUS = "published"

FORBIDDEN_TEXT_PATTERNS = [
    "овен",
    "овна",
    "овну",
    "овнов",
    "телец",
    "тельца",
    "тельцу",
    "тельцов",
    "близнецы",
    "близнецов",
    "рак",
    "рака",
    "раков",
    "лев",
    "льва",
    "львов",
    "дева",
    "девы",
    "девам",
    "весы",
    "весам",
    "скорпион",
    "скорпиона",
    "скорпионов",
    "стрелец",
    "стрельца",
    "стрельцов",
    "козерог",
    "козерога",
    "козерогов",
    "водолей",
    "водолея",
    "водолеев",
    "рыбы",
    "рыбам",
    "змееносец",
    "змееносца",
    "представители знака",
    "люди этого знака",
    "для вашего знака",
    "ваш знак",
    "знак зодиака",
]

SOFT_REPETITION_PATTERNS = [
    "новое окно",
    "приоткрыться",
    "рука может потянуться",
    "тело просит",
    "тёплый чай",
    "короткое сообщение",
    "взгляд",
    "перечитать фразу",
    "вещь не на месте",
    "стол свободнее",
    "свет мягче",
    "не спешите",
    "без спешки",
    "к вечеру",
    "вечером",
    "появится ощущение",
    "останется ощущение",
    "станет легче дышать",
]


def ensure_backend_on_python_path() -> None:
    """
    When this script is executed as:
      python utils/forecast_package_report.py

    Python puts /app/utils on sys.path, but the Flask package lives in /app/app.
    Add backend root (/app) explicitly so imports like `from app import ...` work.
    """
    script_path = Path(__file__).resolve()
    backend_dir = script_path.parents[1]
    backend_dir_str = str(backend_dir)

    if backend_dir_str not in sys.path:
        sys.path.insert(0, backend_dir_str)


def load_local_env() -> None:
    """
    Load .env files without importing Flask config first.

    Supported locations:
    - repository root .env
    - backend/.env
    - current working directory .env
    """
    script_path = Path(__file__).resolve()
    backend_dir = script_path.parents[1]
    repo_root = backend_dir.parent

    for env_path in (
        repo_root / ".env",
        backend_dir / ".env",
        Path.cwd() / ".env",
    ):
        if env_path.exists():
            load_dotenv(env_path, override=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Print a readable quality report for generated forecast package "
            "with provider metadata and prompt variation profiles."
        )
    )
    parser.add_argument(
        "--date",
        required=True,
        help="Target date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--locale",
        default=DEFAULT_LOCALE,
        help=f"Forecast locale. Default: {DEFAULT_LOCALE}",
    )
    parser.add_argument(
        "--forecast-type",
        default=DEFAULT_FORECAST_TYPE,
        help=f"Forecast type. Default: {DEFAULT_FORECAST_TYPE}",
    )
    parser.add_argument(
        "--status",
        default=DEFAULT_STATUS,
        help=f"Forecast status to report. Default: {DEFAULT_STATUS}",
    )
    parser.add_argument(
        "--sign",
        default=None,
        help="Optional single sign_key filter.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Do not print full forecast text.",
    )
    parser.add_argument(
        "--show-metadata",
        action="store_true",
        help="Print extracted prompt variation metadata as JSON for each forecast.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON report instead of text report.",
    )
    return parser.parse_args()


def parse_target_date(raw_value: str) -> date:
    try:
        return date.fromisoformat(raw_value)
    except ValueError as exc:
        raise SystemExit(f"Invalid --date value '{raw_value}'. Expected YYYY-MM-DD.") from exc


def coerce_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value

    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    return {}


def extract_provider_request_payload(request_payload: Any) -> dict[str, Any]:
    """
    OpenAI provider stores original ProviderRequest under:
      request_payload["provider_request"]

    Older/stub payloads may store metadata directly in request_payload.
    This function supports both shapes.
    """
    payload = coerce_mapping(request_payload)

    nested_provider_request = payload.get("provider_request")
    if isinstance(nested_provider_request, dict):
        return nested_provider_request

    return payload


def extract_metadata(request_payload: Any) -> dict[str, Any]:
    provider_request = extract_provider_request_payload(request_payload)
    return coerce_mapping(provider_request.get("metadata"))


def extract_prompt_variation_payload(request_payload: Any) -> dict[str, Any]:
    metadata = extract_metadata(request_payload)
    return coerce_mapping(metadata.get("prompt_variation"))


def extract_prompt_variation_profile(request_payload: Any) -> dict[str, Any]:
    prompt_variation = extract_prompt_variation_payload(request_payload)
    return coerce_mapping(prompt_variation.get("profile"))


def split_sentences(text: str) -> list[str]:
    normalized = " ".join((text or "").split())
    if not normalized:
        return []

    parts = re.split(r"(?<=[.!?…])\s+", normalized)
    return [part.strip() for part in parts if part.strip()]


def get_last_sentence(text: str) -> str:
    sentences = split_sentences(text)
    return sentences[-1] if sentences else ""


def pattern_matches_text(text: str, pattern: str) -> bool:
    """
    Match phrases by substring, but match single-word patterns as whole words.

    This avoids false positives like:
      forbidden pattern "рак" matching "ракурс" / "ракурса"
      forbidden pattern "лев" matching inside unrelated words

    Cyrillic and Latin letters are treated as word letters.
    """
    normalized_text = (text or "").lower()
    normalized_pattern = pattern.lower().strip()

    if not normalized_pattern:
        return False

    if " " in normalized_pattern:
        return normalized_pattern in normalized_text

    regex = re.compile(
        rf"(?<![а-яёa-z]){re.escape(normalized_pattern)}(?![а-яёa-z])",
        flags=re.IGNORECASE,
    )

    return bool(regex.search(normalized_text))


def find_pattern_hits(text: str, patterns: list[str]) -> list[str]:
    return [pattern for pattern in patterns if pattern_matches_text(text, pattern)]


def build_rows(
    *,
    target_date: date,
    locale: str,
    forecast_type: str,
    status: str,
    sign_key: str | None,
) -> list[dict[str, Any]]:
    from app import create_app, db
    from app.models import Forecast, GenerationItem, ZodiacSign

    app = create_app()

    rows: list[dict[str, Any]] = []

    with app.app_context():
        query = (
            db.session.query(Forecast)
            .outerjoin(ZodiacSign, ZodiacSign.key == Forecast.sign_key)
            .filter(
                Forecast.target_date == target_date,
                Forecast.locale == locale,
                Forecast.forecast_type == forecast_type,
                Forecast.status == status,
            )
            .order_by(ZodiacSign.sort_order, Forecast.sign_key)
        )

        if sign_key:
            query = query.filter(Forecast.sign_key == sign_key)

        forecasts = query.all()

        for index, forecast in enumerate(forecasts, start=1):
            item = None
            if forecast.generation_item_id:
                item = db.session.get(GenerationItem, forecast.generation_item_id)

            request_payload = item.request_payload if item else {}
            response_payload = item.response_payload if item else {}

            provider_request = extract_provider_request_payload(request_payload)
            metadata = extract_metadata(request_payload)
            prompt_variation = extract_prompt_variation_payload(request_payload)
            profile = coerce_mapping(prompt_variation.get("profile"))

            text = forecast.text or ""
            title = forecast.title
            combined_title_and_text = " ".join(
                part for part in [title or "", text] if part
            )

            rows.append(
                {
                    "index": index,
                    "forecast_id": forecast.id,
                    "generation_item_id": forecast.generation_item_id,
                    "sign_key": forecast.sign_key,
                    "target_date": forecast.target_date.isoformat(),
                    "locale": forecast.locale,
                    "forecast_type": forecast.forecast_type,
                    "status": forecast.status,
                    "source": forecast.source,
                    "model_name": forecast.model_name,
                    "title": title,
                    "text": text,
                    "sentence_count": len(split_sentences(text)),
                    "last_sentence": get_last_sentence(text),
                    "forbidden_hits": find_pattern_hits(text, FORBIDDEN_TEXT_PATTERNS),
                    "soft_repetition_hits": find_pattern_hits(
                        combined_title_and_text,
                        SOFT_REPETITION_PATTERNS,
                    ),
                    "variation_key": profile.get("key"),
                    "variation_theme": profile.get("theme"),
                    "variation_mood": profile.get("mood"),
                    "variation_tone": profile.get("tone"),
                    "variation_composition": profile.get("composition"),
                    "variation_opening_move": profile.get("opening_move"),
                    "variation_concrete_zone": profile.get("concrete_zone"),
                    "variation_ending_energy": profile.get("ending_energy"),
                    "variation_sentence_style": profile.get("sentence_style"),
                    "variation_avoid": profile.get("avoid"),
                    "metadata_seed": prompt_variation.get("seed"),
                    "has_provider_request": bool(provider_request),
                    "has_response_payload": bool(response_payload),
                    "profile_metadata": profile,
                    "metadata": metadata,
                }
            )

    return rows


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    title_counts = Counter(row["title"] for row in rows if row["title"])
    ending_counts = Counter(row["last_sentence"] for row in rows if row["last_sentence"])
    variation_counts = Counter(row["variation_key"] or "<missing>" for row in rows)
    source_counts = Counter(row["source"] or "<missing>" for row in rows)
    model_counts = Counter(row["model_name"] or "<missing>" for row in rows)

    duplicate_titles = {
        title: count for title, count in title_counts.items() if count > 1
    }
    duplicate_endings = {
        ending: count for ending, count in ending_counts.items() if count > 1
    }

    rows_with_forbidden_hits = [
        {
            "sign_key": row["sign_key"],
            "title": row["title"],
            "hits": row["forbidden_hits"],
        }
        for row in rows
        if row["forbidden_hits"]
    ]

    rows_with_soft_repetition_hits = [
        {
            "sign_key": row["sign_key"],
            "title": row["title"],
            "variation_key": row["variation_key"],
            "hits": row["soft_repetition_hits"],
        }
        for row in rows
        if row["soft_repetition_hits"]
    ]

    return {
        "forecast_count": len(rows),
        "source_counts": dict(source_counts),
        "model_counts": dict(model_counts),
        "variation_counts": dict(variation_counts),
        "duplicate_titles": duplicate_titles,
        "duplicate_endings": duplicate_endings,
        "rows_with_forbidden_hits": rows_with_forbidden_hits,
        "rows_with_soft_repetition_hits": rows_with_soft_repetition_hits,
    }


def print_text_report(
    *,
    target_date: date,
    locale: str,
    forecast_type: str,
    status: str,
    rows: list[dict[str, Any]],
    compact: bool,
    show_metadata: bool,
) -> None:
    summary = build_summary(rows)

    print("\n=== Forecast package report ===")
    print(f"target_date: {target_date.isoformat()}")
    print(f"locale: {locale}")
    print(f"forecast_type: {forecast_type}")
    print(f"status: {status}")
    print(f"forecast_count: {summary['forecast_count']}")

    print("\n=== Source / model ===")
    print(f"sources: {summary['source_counts']}")
    print(f"models: {summary['model_counts']}")

    print("\n=== Variation profiles ===")
    print(f"profiles: {summary['variation_counts']}")

    if "<missing>" in summary["variation_counts"]:
        print(
            "WARNING: some forecasts do not expose variation metadata in "
            "generation item request_payload."
        )

    print("\n=== Duplicate checks ===")
    print(f"duplicate_titles: {summary['duplicate_titles'] or '{}'}")
    print(f"duplicate_endings: {summary['duplicate_endings'] or '{}'}")

    print("\n=== Content checks ===")
    forbidden_rows = summary["rows_with_forbidden_hits"]
    soft_rows = summary["rows_with_soft_repetition_hits"]

    if forbidden_rows:
        print("FORBIDDEN HITS:")
        print(json.dumps(forbidden_rows, ensure_ascii=False, indent=2))
    else:
        print("forbidden_hits: none")

    if soft_rows:
        print("\nSoft repetition hints:")
        print(json.dumps(soft_rows, ensure_ascii=False, indent=2))
    else:
        print("soft_repetition_hits: none")

    for row in rows:
        print("\n" + "=" * 100)
        print(f"{row['index']}. sign_key: {row['sign_key']}")
        print(f"forecast_id: {row['forecast_id']}")
        print(f"generation_item_id: {row['generation_item_id']}")
        print(f"source: {row['source']}")
        print(f"model_name: {row['model_name']}")
        print(f"variation_key: {row['variation_key']}")
        print(f"variation_theme: {row['variation_theme']}")
        print(f"variation_mood: {row['variation_mood']}")
        print(f"title: {row['title']}")
        print(f"sentence_count: {row['sentence_count']}")
        print(f"last_sentence: {row['last_sentence']}")

        if row["forbidden_hits"]:
            print(f"FORBIDDEN_HITS: {row['forbidden_hits']}")

        if row["soft_repetition_hits"]:
            print(f"soft_repetition_hits: {row['soft_repetition_hits']}")

        if show_metadata:
            metadata_payload = {
                "profile": row["profile_metadata"],
                "metadata_seed": row["metadata_seed"],
            }
            print("\n--- variation metadata ---")
            print(json.dumps(metadata_payload, ensure_ascii=False, indent=2))

        if not compact:
            print("-" * 100)
            print(row["text"])


def print_json_report(
    *,
    target_date: date,
    locale: str,
    forecast_type: str,
    status: str,
    rows: list[dict[str, Any]],
) -> None:
    payload = {
        "target_date": target_date.isoformat(),
        "locale": locale,
        "forecast_type": forecast_type,
        "status": status,
        "summary": build_summary(rows),
        "rows": rows,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    ensure_backend_on_python_path()
    load_local_env()
    args = parse_args()

    target_date = parse_target_date(args.date)

    rows = build_rows(
        target_date=target_date,
        locale=args.locale,
        forecast_type=args.forecast_type,
        status=args.status,
        sign_key=args.sign,
    )

    if args.json:
        print_json_report(
            target_date=target_date,
            locale=args.locale,
            forecast_type=args.forecast_type,
            status=args.status,
            rows=rows,
        )
    else:
        print_text_report(
            target_date=target_date,
            locale=args.locale,
            forecast_type=args.forecast_type,
            status=args.status,
            rows=rows,
            compact=args.compact,
            show_metadata=args.show_metadata,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())