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


FORBIDDEN_TIME_ENDING_PHRASES = [
    "к вечеру",
    "к концу дня",
    "к исходу дня",
    "вечером",
]

SOFT_REPETITIVE_WORDS = [
    "ощущение",
    "мягче",
    "мягкий",
    "тише",
    "дышать",
    "пространство",
    "бережный",
    "бережнее",
    "собранность",
]


PROFILES: list[dict[str, str]] = [
    {
        "key": "small_joy",
        "theme": "личные желания, маленькая радость и право выбрать что-то для себя",
        "mood": "тёплый, светлый, чуть вдохновляющий",
        "tone": "мягкий, живой, без излишней серьёзности",
        "composition": "ощущение нехватки → разрешение себе → маленький приятный шаг",
        "opening_move": "начни с внутреннего желания или маленького удовольствия, а не с дел",
        "concrete_zone": "покупка, прогулка, вкус, музыка, личная пауза или маленький выбор для себя",
        "ending_energy": "заверши личным, но конкретным образом: выбранный вкус, любимая мелодия, прогулка или маленькое удовольствие",
        "sentence_style": "4 предложения; без длинного финального обобщения; одно предложение может быть коротким",
        "avoid": "документы, факты, точность, отложенные дела, завершение старого, дедлайны, домашняя уборка, восстановление сил",
    },
    {
        "key": "relationships",
        "theme": "отношения, внимание к другому человеку и изменение атмосферы общения",
        "mood": "человечный, бережный, тёплый",
        "tone": "спокойный, естественный, без морализаторства",
        "composition": "ситуация общения → тонкий нюанс → более тёплый или честный контакт",
        "opening_move": "начни с интонации, взгляда, короткого сообщения или ощущения рядом с человеком",
        "concrete_zone": "разговор, переписка, встреча, жест внимания, семейная или дружеская сцена",
        "ending_energy": "заверши конкретным изменением в контакте: легче спросить, проще ответить, спокойнее услышать друг друга",
        "sentence_style": "4 предложения; без романтического намёка; без слишком поэтического финала",
        "avoid": "романтический намёк, симпатия, флирт, судьбоносность, работа, документы, дедлайны, продуктивность",
    },
    {
        "key": "recovery",
        "theme": "восстановление сил, тело, дом и бережное отношение к себе",
        "mood": "спокойный, заботливый, приземлённый",
        "tone": "мягкий, простой, не медицинский",
        "composition": "сигнал усталости → смена ритма → ощущение опоры",
        "opening_move": "начни с телесного или бытового ощущения, а не с планов и решений",
        "concrete_zone": "сон, еда, вода, прогулка, тишина, удобство, замедление",
        "ending_energy": "заверши конкретным действием заботы о себе, а не абстрактным итогом дня",
        "sentence_style": "4-5 предложений; простые фразы; без медицинских советов и без финала про вечер",
        "avoid": "уборка, порядок, вещи на местах, декор, покупки, переписка, договорённости, документы, факты, споры",
    },
    {
        "key": "new_chance",
        "theme": "новая возможность без давления и осторожный интерес к переменам",
        "mood": "лёгкий, обнадёживающий, с ощущением воздуха",
        "tone": "живой, спокойный, без громких обещаний",
        "composition": "неожиданный шанс → осторожный интерес → первый ненавязчивый шаг",
        "opening_move": "начни с намёка на новое окно возможностей",
        "concrete_zone": "приглашение, случайная идея, новое предложение, смена маршрута, короткий импульс",
        "ending_energy": "заверши тем, что читатель оставляет за собой право выбрать темп перемен",
        "sentence_style": "4 предложения; больше движения, меньше размышлений; без слов «судьба» и «шанс всей жизни»",
        "avoid": "старые дела, завершение, документы, точность, перепроверка, строгая практичность, гарантированный успех",
    },
    {
        "key": "creative_view",
        "theme": "нестандартный взгляд, вдохновение и свежий способ увидеть привычную ситуацию",
        "mood": "лёгкий, любопытный, немного образный",
        "tone": "живой, не пафосный, без туманной эзотерики",
        "composition": "привычная сцена → неожиданный угол зрения → более лёгкий ход",
        "opening_move": "начни с образа, наблюдения или сравнения",
        "concrete_zone": "цвет, свет, предмет, маршрут, случайная фраза, творческая мелочь",
        "ending_energy": "заверши конкретным новым ракурсом или маленьким творческим решением",
        "sentence_style": "4 предложения; можно одно образное сравнение, но без метафорического тумана",
        "avoid": "точность, факты, документы, аккуратность, закрытие хвостов, деловой тон, к вечеру, к концу дня",
    },
    {
        "key": "boundaries",
        "theme": "личные границы, чужие просьбы и спокойное право сказать ясное да или нет",
        "mood": "уверенный, спокойный, поддерживающий",
        "tone": "бережный, прямой, без жёсткости",
        "composition": "чужой запрос → внутренняя проверка → ясный ответ без конфликта",
        "opening_move": "начни с ситуации, где кто-то чего-то ждёт от читателя",
        "concrete_zone": "просьба, звонок, сообщение, договорённость, семейная или рабочая граница",
        "ending_energy": "заверши сохранённым ресурсом или спокойной границей, без морали и без оправданий",
        "sentence_style": "4-5 предложений; фразы уверенные, но не резкие; можно использовать прямую речь",
        "avoid": "отложенные дела, документы, завершение, продуктивность, бытовые мелочи, спор, победа",
    },
    {
        "key": "money_careful",
        "theme": "разумное обращение с деньгами, покупками или ресурсами без обещаний выгоды",
        "mood": "спокойный, взрослый, без тревожности",
        "tone": "практичный, но не офисный",
        "composition": "желание потратить или вложиться → короткая проверка → более зрелый выбор",
        "opening_move": "начни с желания что-то купить, улучшить или упростить",
        "concrete_zone": "покупка, подписка, подарок, мелкая трата, бюджет, вещь для дома",
        "ending_energy": "заверши чувством меры через конкретный выбор: купить, отложить, заменить или отказаться",
        "sentence_style": "4 предложения; без финансовых обещаний; без тревожного тона",
        "avoid": "гарантированная прибыль, удача, богатство, документы, отложенные дела, инвестиционный совет, долги",
    },
    {
        "key": "social_warmth",
        "theme": "социальная лёгкость, маленький знак внимания и приятное взаимодействие",
        "mood": "лёгкий, дружелюбный, светлый",
        "tone": "тёплый, простой, без сентиментальности",
        "composition": "маленький жест → изменение настроения → простое человеческое тепло",
        "opening_move": "начни с жеста, сообщения, улыбки, приглашения или короткого контакта",
        "concrete_zone": "сообщение, встреча, комплимент, приглашение, короткий разговор",
        "ending_energy": "заверши конкретным лёгким взаимодействием, а не глубоким эмоциональным выводом",
        "sentence_style": "4 предложения; бодрее и проще, чем relationships; без глубокой психологичности",
        "avoid": "романтическое напряжение, глубокие разговоры, признания, работа, документы, факты, серьёзные решения",
    },
    {
        "key": "inner_choice",
        "theme": "внутренний выбор, сомнение и честное понимание того, чего хочется на самом деле",
        "mood": "вдумчивый, мягкий, честный",
        "tone": "не назидательный, спокойный, личный",
        "composition": "сомнение → честный внутренний вопрос → более спокойный выбор",
        "opening_move": "начни с внутреннего колебания или вопроса к себе",
        "concrete_zone": "пауза, личное решение, отказ, желание, выбор между двумя вариантами",
        "ending_energy": "заверши конкретным выбором без драматизации: оставить, отпустить, согласиться или отказаться",
        "sentence_style": "можно начать с вопроса; 4 предложения; без затяжного философского финала",
        "avoid": "документы, факты, деловые договорённости, завершение старого, чужие просьбы, судьбоносность",
    },
    {
        "key": "home_mood",
        "theme": "домашняя атмосфера, порядок вокруг себя и влияние пространства на настроение",
        "mood": "уютный, спокойный, собранный",
        "tone": "практичный без офисности, тёплый",
        "composition": "маленькая бытовая деталь → изменение настроения → ощущение собранности",
        "opening_move": "начни с пространства вокруг читателя: дом, вещь, свет, порядок, привычная деталь",
        "concrete_zone": "комната, кухня, одежда, стол, свет, вещь не на месте, маленькая уборка",
        "ending_energy": "заверши конкретной деталью пространства: стол свободнее, свет мягче, вещь на месте",
        "sentence_style": "4 предложения; больше предметности, меньше слов про внутреннее состояние",
        "avoid": "тело, усталость, восстановление сил, прогулка, вода, сон, работа, документы, терапевтичность",
    },
    {
        "key": "romantic_hint",
        "theme": "лёгкий романтический намёк, симпатия или тёплое внимание без обещаний любви",
        "mood": "мягкий, чуть волнующий, деликатный",
        "tone": "тонкий, без сладости и драматизма",
        "composition": "маленький знак внимания → внутренняя реакция → осторожный шаг навстречу",
        "opening_move": "начни с взгляда, сообщения, воспоминания или неожиданно тёплой интонации",
        "concrete_zone": "переписка, встреча, комплимент, пауза в разговоре, личный жест",
        "ending_energy": "заверши открытой возможностью продолжить контакт, но без обещания отношений",
        "sentence_style": "4 предложения; деликатно, без слов «любовь», «судьба», «навсегда»",
        "avoid": "дружеская вежливость, обычная социальная лёгкость, рабочая переписка, документы, факты, судьба, настоящая любовь, гарантии",
    },
    {
        "key": "playful_spontaneity",
        "theme": "спонтанность, лёгкая игра и выход из слишком правильного сценария",
        "mood": "живой, игривый, свободный",
        "tone": "лёгкий, не легкомысленный, с улыбкой",
        "composition": "план нарушается → появляется живой импульс → день становится легче",
        "opening_move": "начни с маленького сбоя в планах или неожиданного желания сделать иначе",
        "concrete_zone": "маршрут, встреча, покупка, приглашение, случайный выбор, короткая авантюра",
        "ending_energy": "заверши бодрым конкретным сдвигом: другой маршрут, неожиданный разговор, новая деталь дня",
        "sentence_style": "4 предложения; чуть быстрее ритм; меньше мягкости, больше движения",
        "avoid": "строгая дисциплина, документы, факты, точность, дедлайны, завершение старого, терапевтичный тон",
    },
    {
        "key": "quiet_confidence",
        "theme": "тихая уверенность, спокойный результат и действие без доказательств окружающим",
        "mood": "собранный, уверенный, ровный",
        "tone": "спокойный, зрелый, без нажима",
        "composition": "желание доказать → отказ от лишнего напряжения → спокойный видимый результат",
        "opening_move": "начни с ситуации, где хочется объяснить или доказать больше необходимого",
        "concrete_zone": "работа, разговор, личное решение, небольшой результат, практический шаг",
        "ending_energy": "заверши видимым результатом без демонстративности, а не абстрактной уверенностью",
        "sentence_style": "4 предложения; допускается деловой контекст, но без канцелярита и без длинных объяснений",
        "avoid": "спор, победа, превосходство, судьбоносность, романтические обещания, документы, бюрократия",
    },
]


SYSTEM_PROMPT = """
Ты пишешь короткие ежедневные персональные прогнозы для сайта гороскопов.

Цель:
дать живой, личный и пригодный для публикации текст на день, а не набор универсальных советов.

Всегда соблюдай:
- Пиши на русском языке.
- Обращайся к читателю на Вы / Вам / Ваш.
- Не называй знак зодиака, дату, астрологические термины и представителей знака.
- Не обещай судьбоносный исход, гарантированную удачу, деньги или любовь.
- Один прогноз должен держаться на одном главном нерве дня, а не на наборе тем.
- Показывай 1–2 конкретных проявления дня, но не превращай текст в список.
- Совет должен быть встроен в наблюдение, а не звучать как команда.
- Избегай канцелярита, офисного productivity tone, эзотерической перегруженности и одинаковых концовок.
- Если тема не про работу, не своди текст к задачам, документам, фактам, дедлайнам и завершению дел.
- Если в запросе есть avoid, used_recent_motifs или used_recent_titles, не используй их ни как основную тему, ни как образ, ни как финальный ход, ни как заголовок.
- Не начинай шаблонно с «Сегодня…».
- Не завершай прогноз словами и конструкциями: «к вечеру», «к концу дня», «к исходу дня», «вечером», «останется ощущение», «появится ощущение», «станет легче дышать».
- Финальное предложение должно завершать мысль дня, а не подводить итог времени суток.
- Не злоупотребляй словами: ощущение, мягче, тише, дышать, пространство, бережный, собранность.
- В одном прогнозе используй не больше одного абстрактного слова из этого ряда, если можно заменить его конкретной сценой.

В каждом запросе будет указан профиль запуска:
theme, mood, tone, composition, opening_move, concrete_zone, ending_energy, sentence_style, avoid.

Следуй именно профилю запуска.
Не выбирай самый безопасный общий сюжет, если задана конкретная тема.

Формат ответа:
верни только JSON по заданной схеме:
- title: короткий небанальный заголовок или null
- text: готовый текст прогноза из 4–5 предложений
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
    profile_keys = [profile["key"] for profile in PROFILES]

    parser = argparse.ArgumentParser(
        description=(
            "Probe horoscope prompt quality with one or more OpenAI requests. "
            "This script does not use Flask app or database."
        )
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
        help=f"Max output tokens per request. Default: {DEFAULT_MAX_OUTPUT_TOKENS}",
    )
    parser.add_argument(
        "--profile",
        choices=profile_keys,
        default=None,
        help=(
            "Profile key to use. "
            "If omitted, profiles are selected without replacement until all are used."
        ),
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=1,
        help="Number of forecasts to generate. Default: 1.",
    )
    parser.add_argument(
        "--recent-window",
        type=int,
        default=5,
        help=(
            "How many recent profile keys and titles to pass into the next prompt "
            "as motifs to avoid. Default: 5."
        ),
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional random seed for reproducible profile selection.",
    )
    parser.add_argument(
        "--show-prompt",
        action="store_true",
        help="Print the final prompts before each OpenAI request.",
    )
    parser.add_argument(
        "--list-profiles",
        action="store_true",
        help="List available profiles and exit without making an OpenAI request.",
    )

    return parser.parse_args()


def get_profile_by_key(key: str) -> dict[str, str]:
    for profile in PROFILES:
        if profile["key"] == key:
            return profile

    raise ValueError(f"Unknown profile key: {key}")


def build_profile_sequence(
    *,
    selected_profile_key: str | None,
    batch_size: int,
    seed: int | None,
) -> list[dict[str, str]]:
    if batch_size < 1:
        raise ValueError("--batch must be greater than or equal to 1.")

    if selected_profile_key:
        profile = get_profile_by_key(selected_profile_key)
        return [profile for _ in range(batch_size)]

    rng = random.Random(seed)
    pool = PROFILES.copy()
    rng.shuffle(pool)

    selected: list[dict[str, str]] = []

    while len(selected) < batch_size:
        if not pool:
            pool = PROFILES.copy()
            rng.shuffle(pool)

        selected.append(pool.pop())

    return selected


def build_user_prompt(
    *,
    profile: dict[str, str],
    used_recent_motifs: list[str],
    used_recent_titles: list[str],
) -> str:
    return f"""
Сгенерируй один ежедневный персональный прогноз.

Профиль этого запуска:
- theme: {profile["theme"]}
- mood: {profile["mood"]}
- tone: {profile["tone"]}
- composition: {profile["composition"]}
- opening_move: {profile["opening_move"]}
- concrete_zone: {profile["concrete_zone"]}
- ending_energy: {profile["ending_energy"]}
- sentence_style: {profile["sentence_style"]}
- avoid: {profile["avoid"]}

Недавние мотивы в этом батче, которые нельзя повторять:
{json.dumps(used_recent_motifs, ensure_ascii=False)}

Недавние заголовки в этом батче, которые нельзя повторять:
{json.dumps(used_recent_titles, ensure_ascii=False)}

Особенно избегай финалов и формул:
{json.dumps(FORBIDDEN_TIME_ENDING_PHRASES, ensure_ascii=False)}

Не злоупотребляй мягкими абстрактными словами:
{json.dumps(SOFT_REPETITIVE_WORDS, ensure_ascii=False)}

Требования:
- Следуй профилю запуска, но не повторяй его формулировки дословно.
- Держи один основной фокус от начала до конца.
- Прояви тему через concrete_zone.
- Соблюдай sentence_style.
- Не перечисляй темы подряд.
- Не делай текст похожим на инструкцию, чеклист или список советов.
- Не привязывай текст к конкретному знаку зодиака или конкретной дате.
- Не используй мотивы и слова из avoid, used_recent_motifs и used_recent_titles.
- Сделай ритм и синтаксис непохожими на недавние тексты.
- Если тема не про работу, не возвращайся к сюжетам про документы, факты, точность, дедлайны, завершение старого и отложенные дела.
- Финальное предложение должно быть конкретным и тематическим, а не итогом про вечер или общее ощущение.
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


def parse_output_json(raw_text: str) -> dict[str, Any]:
    parsed = json.loads(raw_text)

    if not isinstance(parsed, dict):
        raise ValueError("OpenAI response JSON is not an object.")

    if "text" not in parsed or not isinstance(parsed["text"], str) or not parsed["text"].strip():
        raise ValueError("OpenAI response JSON does not contain a non-empty text field.")

    if "title" not in parsed:
        parsed["title"] = None

    if parsed["title"] is not None and not isinstance(parsed["title"], str):
        parsed["title"] = None

    return parsed


def print_profiles() -> None:
    print("Available profiles:\n")

    for profile in PROFILES:
        print(f"- {profile['key']}")
        print(f"  theme: {profile['theme']}")
        print(f"  mood: {profile['mood']}")
        print(f"  tone: {profile['tone']}")
        print(f"  sentence_style: {profile['sentence_style']}")
        print(f"  avoid: {profile['avoid']}")
        print()


def get_usage_payload(response: Any) -> dict[str, Any] | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None

    if hasattr(usage, "model_dump"):
        return usage.model_dump(mode="json")

    if isinstance(usage, dict):
        return usage

    return {"repr": repr(usage)}


def print_usage(response: Any) -> None:
    usage_payload = get_usage_payload(response)
    if usage_payload is None:
        return

    print("\n=== Usage ===")
    print(json.dumps(usage_payload, ensure_ascii=False, indent=2))


def find_quality_warnings(text: str) -> list[str]:
    text_lower = text.lower()
    warnings: list[str] = []

    for phrase in FORBIDDEN_TIME_ENDING_PHRASES:
        if phrase in text_lower:
            warnings.append(f"contains forbidden time-ending phrase: {phrase}")

    soft_word_hits = [
        word for word in SOFT_REPETITIVE_WORDS
        if word.lower() in text_lower
    ]

    if len(soft_word_hits) > 2:
        warnings.append(
            "uses many soft/repetitive words: "
            + ", ".join(sorted(set(soft_word_hits)))
        )

    if text_lower.startswith("сегодня"):
        warnings.append("starts with шаблонное «Сегодня»")

    if text_lower.startswith("в этот день"):
        warnings.append("starts with шаблонное «В этот день»")

    return warnings


def call_openai(
    *,
    client: OpenAI,
    model: str,
    max_output_tokens: int,
    user_prompt: str,
) -> Any:
    return client.responses.create(
        model=model,
        instructions=SYSTEM_PROMPT,
        input=user_prompt,
        max_output_tokens=max_output_tokens,
        text={
            "format": {
                "type": "json_schema",
                "name": "horoscope_forecast_probe",
                "strict": True,
                "schema": OUTPUT_SCHEMA,
            }
        },
    )


def print_single_result(
    *,
    index: int,
    batch_size: int,
    model: str,
    profile: dict[str, str],
    response: Any,
    raw_text: str,
    parsed: dict[str, Any],
    warnings: list[str],
) -> None:
    print("\n" + "=" * 80)
    print(f"=== OpenAI prompt probe {index}/{batch_size} ===")
    print(f"model: {model}")
    print(f"profile: {profile['key']}")
    print(f"theme: {profile['theme']}")

    request_id = getattr(response, "_request_id", None)
    if request_id:
        print(f"request_id: {request_id}")

    print_usage(response)

    if warnings:
        print("\n=== Quality warnings ===")
        for warning in warnings:
            print(f"- {warning}")

    print("\n=== Raw output_text ===")
    print(raw_text)

    print("\n=== Parsed JSON ===")
    print(json.dumps(parsed, ensure_ascii=False, indent=2))

    print("\n=== Forecast text ===")
    print(parsed["text"])


def print_batch_summary(results: list[dict[str, Any]]) -> None:
    print("\n" + "=" * 80)
    print("=== Batch summary ===")

    for index, result in enumerate(results, start=1):
        title = result["title"] or "null"
        warning_count = len(result["warnings"])
        warning_suffix = f" | warnings={warning_count}" if warning_count else ""
        print(f"{index}. [{result['profile_key']}] {title}{warning_suffix}")

    total_warnings = sum(len(result["warnings"]) for result in results)

    print("\n=== Batch quality ===")
    print(f"items: {len(results)}")
    print(f"total_warnings: {total_warnings}")

    if total_warnings:
        print("\nWarnings by item:")
        for index, result in enumerate(results, start=1):
            if not result["warnings"]:
                continue

            print(f"{index}. [{result['profile_key']}]")
            for warning in result["warnings"]:
                print(f"   - {warning}")

    print("\n=== Forecasts only ===")

    for index, result in enumerate(results, start=1):
        title = result["title"]
        text = result["text"]

        print(f"\n{index}. profile={result['profile_key']}")
        if title:
            print(f"Title: {title}")
        print(text)


def main() -> int:
    load_local_env()
    args = parse_args()

    if args.list_profiles:
        print_profiles()
        return 0

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is missing. Add it to .env or export it before running."
        )

    profile_sequence = build_profile_sequence(
        selected_profile_key=args.profile,
        batch_size=args.batch,
        seed=args.seed,
    )

    client = OpenAI(
        api_key=api_key,
        timeout=args.timeout,
    )

    used_recent_motifs: list[str] = []
    used_recent_titles: list[str] = []
    results: list[dict[str, Any]] = []

    for index, profile in enumerate(profile_sequence, start=1):
        recent_motifs = used_recent_motifs[-args.recent_window :]
        recent_titles = used_recent_titles[-args.recent_window :]

        user_prompt = build_user_prompt(
            profile=profile,
            used_recent_motifs=recent_motifs,
            used_recent_titles=recent_titles,
        )

        if args.show_prompt:
            print("\n" + "=" * 80)
            print(f"=== Prompt {index}/{args.batch} ===")
            print("\n=== System prompt ===")
            print(SYSTEM_PROMPT)
            print("\n=== User prompt ===")
            print(user_prompt)

        response = call_openai(
            client=client,
            model=args.model,
            max_output_tokens=args.max_output_tokens,
            user_prompt=user_prompt,
        )

        raw_text = extract_output_text(response)
        parsed = parse_output_json(raw_text)

        title = parsed.get("title")
        text = parsed["text"]
        warnings = find_quality_warnings(text)

        print_single_result(
            index=index,
            batch_size=args.batch,
            model=args.model,
            profile=profile,
            response=response,
            raw_text=raw_text,
            parsed=parsed,
            warnings=warnings,
        )

        used_recent_motifs.append(profile["key"])
        if isinstance(title, str) and title.strip():
            used_recent_titles.append(title.strip())

        results.append(
            {
                "profile_key": profile["key"],
                "theme": profile["theme"],
                "title": title,
                "text": text,
                "warnings": warnings,
            }
        )

    if args.batch > 1:
        print_batch_summary(results)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())