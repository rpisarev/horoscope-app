from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI


DEFAULT_MODEL = "gpt-5.2"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_OUTPUT_TOKENS = 500


SYSTEM_PROMPT = """
Ты пишешь короткие ежедневные персональные прогнозы для сайта гороскопов.

Важные правила:
- Пиши на русском языке.
- Обращайся к читателю напрямую: Вас, Вам, Ваш, Ваши.
- Не называй знак зодиака.
- Не упоминай дату.
- Не используй фразы: знак зодиака, ваш знак, представители знака, люди этого знака.
- Не обещай гарантированный успех.
- Тон: спокойный, доброжелательный, немного вдохновляющий, без мистического пафоса.
- Длина: 4-5 предложений.
- Верни только JSON по заданной схеме.
""".strip()


USER_PROMPT = """
Сгенерируй один ежедневный персональный прогноз для читателя.

Фокус прогноза:
- настроение дня;
- работа или личные дела;
- отношения с людьми;
- небольшой практический совет.

Не привязывай текст к конкретному знаку зодиака или конкретной дате.
""".strip()


OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "text"],
    "properties": {
        "title": {
            "type": ["string", "null"],
            "description": "Короткий необязательный заголовок прогноза.",
        },
        "text": {
            "type": "string",
            "description": "Готовый текст прогноза на русском языке, 4-5 предложений.",
        },
    },
}


def load_local_env() -> None:
    """
    Load .env files without requiring Flask or project config.

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
        description="Make exactly one OpenAI request with a hardcoded horoscope prompt."
    )
    parser.add_argument(
        "--model",
        default=os.getenv("OPENAI_MODEL", DEFAULT_MODEL),
        help=f"OpenAI model name. Default: env OPENAI_MODEL or {DEFAULT_MODEL}",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.getenv("OPENAI_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)),
        help=f"Request timeout in seconds. Default: {DEFAULT_TIMEOUT_SECONDS}",
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", DEFAULT_MAX_OUTPUT_TOKENS)),
        help=f"Max output tokens. Default: {DEFAULT_MAX_OUTPUT_TOKENS}",
    )
    return parser.parse_args()


def extract_output_text(response: Any) -> str:
    """
    Prefer SDK convenience property, then fall back to explicit output traversal.
    """
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    collected: list[str] = []
    response_payload = response.model_dump(mode="json")

    for item in response_payload.get("output", []):
        if not isinstance(item, dict):
            continue

        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue

            text = content.get("text")
            if isinstance(text, str) and text.strip():
                collected.append(text.strip())

    if collected:
        return "\n".join(collected).strip()

    raise RuntimeError("OpenAI response did not contain output text.")


def main() -> int:
    load_local_env()
    args = parse_args()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is missing. Add it to .env or export it before running."
        )

    client = OpenAI(
        api_key=api_key,
        timeout=args.timeout,
    )

    response = client.responses.create(
        model=args.model,
        instructions=SYSTEM_PROMPT,
        input=USER_PROMPT,
        max_output_tokens=args.max_output_tokens,
        text={
            "format": {
                "type": "json_schema",
                "name": "horoscope_forecast_probe",
                "strict": True,
                "schema": OUTPUT_SCHEMA,
            }
        },
    )

    raw_text = extract_output_text(response)

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        parsed = None

    print("\n=== OpenAI prompt probe ===")
    print(f"model: {args.model}")

    request_id = getattr(response, "_request_id", None)
    if request_id:
        print(f"request_id: {request_id}")

    print("\n=== Raw output_text ===")
    print(raw_text)

    if parsed is not None:
        print("\n=== Parsed JSON ===")
        print(json.dumps(parsed, ensure_ascii=False, indent=2))

        print("\n=== Forecast text ===")
        print(parsed.get("text", ""))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
