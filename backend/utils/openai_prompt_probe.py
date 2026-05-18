from __future__ import annotations

import argparse
import json
import os
import random
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI


DEFAULT_MODEL = "gpt-5.4-mini"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_OUTPUT_TOKENS = 500


VARIATIONS: list[dict[str, str]] = [
    {
        "key": "small_joy",
        "theme": "личные желания, маленькая радость и право выбрать что-то для себя",
        "tone": "тёплый, мягко-вдохновляющий, без излишней серьёзности",
        "composition": "ощущение нехватки → разрешение себе → маленький приятный шаг",
        "opening": "начни не с дела и не с работы, а с внутреннего ощущения или желания",
        "avoid": "документы, факты, точность, отложенные дела, завершение старого, деловые переговоры",
    },
    {
        "key": "relationships",
        "theme": "отношения, внимание к другому человеку и изменение атмосферы общения",
        "tone": "человечный, спокойный, бережный",
        "composition": "ситуация общения → тонкий нюанс → более тёплый или честный контакт",
        "opening": "начни с разговора, интонации, взгляда или ощущения рядом с человеком",
        "avoid": "работа, документы, дедлайны, продуктивность, списки задач, завершение начатого",
    },
    {
        "key": "recovery",
        "theme": "восстановление сил, тело, дом и бережное отношение к себе",
        "tone": "заботливый, спокойный, приземлённый",
        "composition": "сигнал усталости → смена ритма → ощущение опоры",
        "opening": "начни с телесного или бытового ощущения, а не с планов и решений",
        "avoid": "переписка, договорённости, документы, факты, доказательства, споры",
    },
    {
        "key": "new_chance",
        "theme": "новая возможность без давления и осторожный интерес к переменам",
        "tone": "лёгкий, обнадёживающий, с ощущением воздуха",
        "composition": "неожиданная возможность → осторожный интерес → первый ненавязчивый шаг",
        "opening": "начни с намёка на новое окно возможностей, но без громких обещаний",
        "avoid": "старые дела, завершение, документы, точность, перепроверка, строгая практичность",
    },
    {
        "key": "creative_view",
        "theme": "нестандартный взгляд, вдохновение и свежий способ увидеть привычную ситуацию",
        "tone": "живой, немного образный, но не пафосный",
        "composition": "привычная сцена → неожиданный угол зрения → более лёгкий ход",
        "opening": "начни с образа, наблюдения или сравнения, но не превращай текст в метафорическую прозу",
        "avoid": "точность, факты, документы, аккуратность, конкретика, закрытие хвостов",
    },
    {
        "key": "boundaries",
        "theme": "личные границы, чужие просьбы и спокойное право сказать ясное «да» или «нет»",
        "tone": "уверенный, спокойный, поддерживающий",
        "composition": "чужой запрос → внутренняя проверка → ясный ответ без конфликта",
        "opening": "начни с ситуации, где кто-то чего-то ждёт от читателя",
        "avoid": "отложенные дела, документы, завершение, продуктивность, бытовые мелочи",
    },
    {
        "key": "money_careful",
        "theme": "разумное обращение с деньгами, покупками или ресурсами без обещаний выгоды",
        "tone": "практичный, спокойный, без тревожности",
        "composition": "желание потратить или вложиться → короткая проверка → более зрелый выбор",
        "opening": "начни с желания что-то купить, улучшить или упростить",
        "avoid": "гарантированная прибыль, удача, богатство, документы, отложенные дела, разговоры о чувствах",
    },
    {
        "key": "social_warmth",
        "theme": "социальная лёгкость, маленький знак внимания и приятное взаимодействие",
        "tone": "лёгкий, дружелюбный, чуть светлее обычного",
        "composition": "маленький жест → изменение настроения → простое человеческое тепло",
        "opening": "начни с жеста, сообщения, улыбки, приглашения или короткого контакта",
        "avoid": "работа, документы, факты, завершение дел, серьёзные решения, внутреннее напряжение",
    },
    {
        "key": "inner_choice",
        "theme": "внутренний выбор, сомнение и честное понимание того, чего хочется на самом деле",
        "tone": "вдумчивый, мягкий, не назидательный",
        "composition": "сомнение → честный внутренний вопрос → более спокойный выбор",
        "opening": "начни с внутреннего колебания или вопроса к себе",
        "avoid": "документы, факты, деловые договорённости, завершение старого, чужие просьбы",
    },
    {
        "key": "home_mood",
        "theme": "домашняя атмосфера, порядок вокруг себя и влияние пространства на настроение",
        "tone": "уютный, спокойный, практичный без офисности",
        "composition": "маленькая бытовая деталь → изменение настроения → ощущение собранности",
        "opening": "начни с пространства вокруг читателя: дома, вещи, свет, порядок, привычная деталь",
        "avoid": "работа, документы, переговоры, дедлайны, точные формулировки, карьерные задачи",
    },
]


SYSTEM_PROMPT = """
Ты пишешь короткие ежедневные персональные прогнозы для сайта гороскопов.

Главная задача:
создать ощущение личного, живого и полезного прогноза на день, а не универсальный совет из списка.

Язык и обращение:
- Пиши на русском языке.
- Обращайся к читателю напрямую: Вы, Вас, Вам, Ваш, Ваши.
- Не называй знак зодиака.
- Не упоминай дату.
- Не используй фразы: знак зодиака, ваш знак, представители знака, люди этого знака.

Стиль:
- Тон спокойный, доброжелательный, уверенный.
- Можно использовать лёгкую образность, но без эзотерической перегруженности.
- Не обещай гарантированный успех, деньги, любовь или судьбоносные события.
- Не пиши слишком общими фразами.
- Избегай канцелярита и повторяющихся шаблонов.
- Текст должен звучать как готовый прогноз для публикации, а не как инструкция.

Вариативность:
- В каждом запросе будет указан вариант этого запуска: тема, тон, композиция, начало и мотивы, которых нужно избегать.
- Следуй именно варианту этого запуска.
- Не выбирай самый безопасный общий сюжет, если задана конкретная тема.
- Если указаны избегаемые мотивы, не используй их ни как основную тему, ни как финальный совет.
- Не возвращайся автоматически к сюжетам про точность, факты, документы, отложенные дела и завершение, если они не заданы явно.

Формат:
- 4-5 предложений.
- Верни только JSON по заданной схеме.
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
    variation_keys = [variation["key"] for variation in VARIATIONS]

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
    parser.add_argument(
        "--variation",
        choices=variation_keys,
        default=None,
        help=(
            "Variation profile to use. "
            "If omitted, one profile is selected randomly for this run."
        ),
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional random seed for reproducible random variation selection.",
    )
    parser.add_argument(
        "--show-prompt",
        action="store_true",
        help="Print the final user prompt before making the OpenAI request.",
    )
    parser.add_argument(
        "--list-variations",
        action="store_true",
        help="List available variation keys and exit without making an OpenAI request.",
    )

    return parser.parse_args()


def get_variation(key: str | None, seed: int | None) -> dict[str, str]:
    if key:
        for variation in VARIATIONS:
            if variation["key"] == key:
                return variation

        raise ValueError(f"Unknown variation key: {key}")

    rng = random.Random(seed)
    return rng.choice(VARIATIONS)


def build_user_prompt(variation: dict[str, str]) -> str:
    return f"""
Сгенерируй один ежедневный персональный прогноз для читателя.

Вариант этого запуска:
- главная тема: {variation["theme"]}
- тон: {variation["tone"]}
- композиция: {variation["composition"]}
- начало: {variation["opening"]}
- избегай мотивов: {variation["avoid"]}

Правила:
- Не перечисляй темы подряд.
- Не делай текст похожим на инструкцию, чеклист или список советов.
- Не привязывай текст к конкретному знаку зодиака или конкретной дате.
- Не используй слова и мотивы из блока “избегай мотивов”.
- Не повторяй дословно формулировки из варианта запуска.
- Не завершай каждый прогноз одинаковой фразой про вечер, облегчение или ясность.
- Не превращай текст в офисный productivity-advice, если тема этого запуска не про работу.
- Сделай прогноз живым, но не слишком литературным.
""".strip()


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


def print_variations() -> None:
    print("Available variations:\n")

    for variation in VARIATIONS:
        print(f"- {variation['key']}")
        print(f"  theme: {variation['theme']}")
        print(f"  tone: {variation['tone']}")
        print(f"  avoid: {variation['avoid']}")
        print()


def print_usage(response: Any) -> None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return

    if hasattr(usage, "model_dump"):
        usage_payload = usage.model_dump(mode="json")
    elif isinstance(usage, dict):
        usage_payload = usage
    else:
        usage_payload = {"repr": repr(usage)}

    print("\n=== Usage ===")
    print(json.dumps(usage_payload, ensure_ascii=False, indent=2))


def main() -> int:
    load_local_env()
    args = parse_args()

    if args.list_variations:
        print_variations()
        return 0

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is missing. Add it to .env or export it before running."
        )

    variation = get_variation(args.variation, args.seed)
    user_prompt = build_user_prompt(variation)

    if args.show_prompt:
        print("\n=== System prompt ===")
        print(SYSTEM_PROMPT)
        print("\n=== User prompt ===")
        print(user_prompt)

    client = OpenAI(
        api_key=api_key,
        timeout=args.timeout,
    )

    response = client.responses.create(
        model=args.model,
        instructions=SYSTEM_PROMPT,
        input=user_prompt,
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
    print(f"variation: {variation['key']}")
    print(f"theme: {variation['theme']}")

    request_id = getattr(response, "_request_id", None)
    if request_id:
        print(f"request_id: {request_id}")

    print_usage(response)

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