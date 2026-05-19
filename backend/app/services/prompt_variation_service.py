from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class PromptVariationProfile:
    key: str
    theme: str
    mood: str
    tone: str
    composition: str
    opening_move: str
    concrete_zone: str
    ending_energy: str
    sentence_style: str
    avoid: str

    def to_prompt_variables(self) -> dict[str, str]:
        return {
            "prompt_variation_key": self.key,
            "prompt_variation_theme": self.theme,
            "prompt_variation_mood": self.mood,
            "prompt_variation_tone": self.tone,
            "prompt_variation_composition": self.composition,
            "prompt_variation_opening_move": self.opening_move,
            "prompt_variation_concrete_zone": self.concrete_zone,
            "prompt_variation_ending_energy": self.ending_energy,
            "prompt_variation_sentence_style": self.sentence_style,
            "prompt_variation_avoid": self.avoid,
        }

    def to_metadata(self) -> dict[str, str]:
        return {
            "key": self.key,
            "theme": self.theme,
            "mood": self.mood,
            "tone": self.tone,
            "composition": self.composition,
            "opening_move": self.opening_move,
            "concrete_zone": self.concrete_zone,
            "ending_energy": self.ending_energy,
            "sentence_style": self.sentence_style,
            "avoid": self.avoid,
        }


PROMPT_VARIATION_PROFILES: tuple[PromptVariationProfile, ...] = (
    PromptVariationProfile(
        key="small_joy",
        theme="личные желания, маленькая радость и право выбрать что-то для себя",
        mood="тёплый, светлый, чуть вдохновляющий",
        tone="мягкий, живой, без излишней серьёзности",
        composition="ощущение нехватки → разрешение себе → маленький приятный шаг",
        opening_move="начни с внутреннего желания или маленького удовольствия, а не с дел",
        concrete_zone=(
            "покупка, прогулка, вкус, музыка, личная пауза или маленький выбор для себя"
        ),
        ending_energy=(
            "заверши личным, но конкретным образом: выбранный вкус, любимая мелодия, "
            "прогулка или маленькое удовольствие"
        ),
        sentence_style=(
            "4 предложения; без длинного финального обобщения; одно предложение может быть коротким"
        ),
        avoid=(
            "документы, факты, точность, отложенные дела, завершение старого, дедлайны, "
            "домашняя уборка, восстановление сил"
        ),
    ),
    PromptVariationProfile(
        key="relationships",
        theme="отношения, внимание к другому человеку и изменение атмосферы общения",
        mood="человечный, бережный, тёплый",
        tone="спокойный, естественный, без морализаторства",
        composition="ситуация общения → тонкий нюанс → более тёплый или честный контакт",
        opening_move=(
            "начни с интонации, взгляда, короткого сообщения или ощущения рядом с человеком"
        ),
        concrete_zone=(
            "разговор, переписка, встреча, жест внимания, семейная или дружеская сцена"
        ),
        ending_energy=(
            "заверши конкретным изменением в контакте: легче спросить, проще ответить, "
            "спокойнее услышать друг друга"
        ),
        sentence_style="4 предложения; без романтического намёка; без слишком поэтического финала",
        avoid=(
            "романтический намёк, симпатия, флирт, судьбоносность, работа, документы, "
            "дедлайны, продуктивность"
        ),
    ),
    PromptVariationProfile(
        key="recovery",
        theme="восстановление сил, тело, дом и бережное отношение к себе",
        mood="спокойный, заботливый, приземлённый",
        tone="мягкий, простой, не медицинский",
        composition="сигнал усталости → смена ритма → ощущение опоры",
        opening_move="начни с телесного или бытового ощущения, а не с планов и решений",
        concrete_zone="сон, еда, вода, прогулка, тишина, удобство, замедление",
        ending_energy="заверши конкретным действием заботы о себе, а не абстрактным итогом дня",
        sentence_style=(
            "4-5 предложений; простые фразы; без медицинских советов и без финала про вечер"
        ),
        avoid=(
            "уборка, порядок, вещи на местах, декор, покупки, переписка, договорённости, "
            "документы, факты, споры"
        ),
    ),
    PromptVariationProfile(
        key="new_chance",
        theme="новая возможность без давления и осторожный интерес к переменам",
        mood="лёгкий, обнадёживающий, с ощущением воздуха",
        tone="живой, спокойный, без громких обещаний",
        composition="неожиданный шанс → осторожный интерес → первый ненавязчивый шаг",
        opening_move="начни с намёка на новое окно возможностей",
        concrete_zone=(
            "приглашение, случайная идея, новое предложение, смена маршрута, короткий импульс"
        ),
        ending_energy="заверши тем, что читатель оставляет за собой право выбрать темп перемен",
        sentence_style=(
            "4 предложения; больше движения, меньше размышлений; без слов «судьба» "
            "и «шанс всей жизни»"
        ),
        avoid=(
            "старые дела, завершение, документы, точность, перепроверка, строгая практичность, "
            "гарантированный успех"
        ),
    ),
    PromptVariationProfile(
        key="creative_view",
        theme="нестандартный взгляд, вдохновение и свежий способ увидеть привычную ситуацию",
        mood="лёгкий, любопытный, немного образный",
        tone="живой, не пафосный, без туманной эзотерики",
        composition="привычная сцена → неожиданный угол зрения → более лёгкий ход",
        opening_move="начни с образа, наблюдения или сравнения",
        concrete_zone=(
            "цвет, свет, предмет, маршрут, случайная фраза, творческая мелочь"
        ),
        ending_energy="заверши конкретным новым ракурсом или маленьким творческим решением",
        sentence_style=(
            "4 предложения; можно одно образное сравнение, но без метафорического тумана"
        ),
        avoid=(
            "точность, факты, документы, аккуратность, закрытие хвостов, деловой тон, "
            "к вечеру, к концу дня"
        ),
    ),
    PromptVariationProfile(
        key="boundaries",
        theme="личные границы, чужие просьбы и спокойное право сказать ясное да или нет",
        mood="уверенный, спокойный, поддерживающий",
        tone="бережный, прямой, без жёсткости",
        composition="чужой запрос → внутренняя проверка → ясный ответ без конфликта",
        opening_move="начни с ситуации, где кто-то чего-то ждёт от читателя",
        concrete_zone="просьба, звонок, сообщение, договорённость, семейная или рабочая граница",
        ending_energy="заверши сохранённым ресурсом или спокойной границей, без морали и без оправданий",
        sentence_style=(
            "4-5 предложений; фразы уверенные, но не резкие; можно использовать прямую речь"
        ),
        avoid="отложенные дела, документы, завершение, продуктивность, бытовые мелочи, спор, победа",
    ),
    PromptVariationProfile(
        key="money_careful",
        theme="разумное обращение с деньгами, покупками или ресурсами без обещаний выгоды",
        mood="спокойный, взрослый, без тревожности",
        tone="практичный, но не офисный",
        composition="желание потратить или вложиться → короткая проверка → более зрелый выбор",
        opening_move="начни с желания что-то купить, улучшить или упростить",
        concrete_zone="покупка, подписка, подарок, мелкая трата, бюджет, вещь для дома",
        ending_energy=(
            "заверши чувством меры через конкретный выбор: купить, отложить, заменить или отказаться"
        ),
        sentence_style="4 предложения; без финансовых обещаний; без тревожного тона",
        avoid=(
            "гарантированная прибыль, удача, богатство, документы, отложенные дела, "
            "инвестиционный совет, долги"
        ),
    ),
    PromptVariationProfile(
        key="social_warmth",
        theme="социальная лёгкость, маленький знак внимания и приятное взаимодействие",
        mood="лёгкий, дружелюбный, светлый",
        tone="тёплый, простой, без сентиментальности",
        composition="маленький жест → изменение настроения → простое человеческое тепло",
        opening_move="начни с жеста, сообщения, улыбки, приглашения или короткого контакта",
        concrete_zone="сообщение, встреча, комплимент, приглашение, короткий разговор",
        ending_energy="заверши конкретным лёгким взаимодействием, а не глубоким эмоциональным выводом",
        sentence_style=(
            "4 предложения; бодрее и проще, чем relationships; без глубокой психологичности"
        ),
        avoid=(
            "романтическое напряжение, глубокие разговоры, признания, работа, документы, "
            "факты, серьёзные решения"
        ),
    ),
    PromptVariationProfile(
        key="inner_choice",
        theme="внутренний выбор, сомнение и честное понимание того, чего хочется на самом деле",
        mood="вдумчивый, мягкий, честный",
        tone="не назидательный, спокойный, личный",
        composition="сомнение → честный внутренний вопрос → более спокойный выбор",
        opening_move="начни с внутреннего колебания или вопроса к себе",
        concrete_zone="пауза, личное решение, отказ, желание, выбор между двумя вариантами",
        ending_energy=(
            "заверши конкретным выбором без драматизации: оставить, отпустить, согласиться или отказаться"
        ),
        sentence_style="можно начать с вопроса; 4 предложения; без затяжного философского финала",
        avoid=(
            "документы, факты, деловые договорённости, завершение старого, чужие просьбы, "
            "судьбоносность"
        ),
    ),
    PromptVariationProfile(
        key="home_mood",
        theme="домашняя атмосфера, порядок вокруг себя и влияние пространства на настроение",
        mood="уютный, спокойный, собранный",
        tone="практичный без офисности, тёплый",
        composition="маленькая бытовая деталь → изменение настроения → ощущение собранности",
        opening_move=(
            "начни с пространства вокруг читателя: дом, вещь, свет, порядок, привычная деталь"
        ),
        concrete_zone="комната, кухня, одежда, стол, свет, вещь не на месте, маленькая уборка",
        ending_energy="заверши конкретной деталью пространства: стол свободнее, свет мягче, вещь на месте",
        sentence_style="4 предложения; больше предметности, меньше слов про внутреннее состояние",
        avoid=(
            "тело, усталость, восстановление сил, прогулка, вода, сон, работа, документы, "
            "терапевтичность"
        ),
    ),
    PromptVariationProfile(
        key="romantic_hint",
        theme="лёгкий романтический намёк, симпатия или тёплое внимание без обещаний любви",
        mood="мягкий, чуть волнующий, деликатный",
        tone="тонкий, без сладости и драматизма",
        composition="маленький знак внимания → внутренняя реакция → осторожный шаг навстречу",
        opening_move="начни с взгляда, сообщения, воспоминания или неожиданно тёплой интонации",
        concrete_zone="переписка, встреча, комплимент, пауза в разговоре, личный жест",
        ending_energy="заверши открытой возможностью продолжить контакт, но без обещания отношений",
        sentence_style="4 предложения; деликатно, без слов «любовь», «судьба», «навсегда»",
        avoid=(
            "дружеская вежливость, обычная социальная лёгкость, рабочая переписка, документы, "
            "факты, судьба, настоящая любовь, гарантии"
        ),
    ),
    PromptVariationProfile(
        key="playful_spontaneity",
        theme="спонтанность, лёгкая игра и выход из слишком правильного сценария",
        mood="живой, игривый, свободный",
        tone="лёгкий, не легкомысленный, с улыбкой",
        composition="план нарушается → появляется живой импульс → день становится легче",
        opening_move="начни с маленького сбоя в планах или неожиданного желания сделать иначе",
        concrete_zone="маршрут, встреча, покупка, приглашение, случайный выбор, короткая авантюра",
        ending_energy=(
            "заверши бодрым конкретным сдвигом: другой маршрут, неожиданный разговор, "
            "новая деталь дня"
        ),
        sentence_style="4 предложения; чуть быстрее ритм; меньше мягкости, больше движения",
        avoid=(
            "строгая дисциплина, документы, факты, точность, дедлайны, завершение старого, "
            "терапевтичный тон"
        ),
    ),
    PromptVariationProfile(
        key="quiet_confidence",
        theme="тихая уверенность, спокойный результат и действие без доказательств окружающим",
        mood="собранный, уверенный, ровный",
        tone="спокойный, зрелый, без нажима",
        composition="желание доказать → отказ от лишнего напряжения → спокойный видимый результат",
        opening_move="начни с ситуации, где хочется объяснить или доказать больше необходимого",
        concrete_zone="работа, разговор, личное решение, небольшой результат, практический шаг",
        ending_energy=(
            "заверши видимым результатом без демонстративности, а не абстрактной уверенностью"
        ),
        sentence_style=(
            "4 предложения; допускается деловой контекст, но без канцелярита и без длинных объяснений"
        ),
        avoid=(
            "спор, победа, превосходство, судьбоносность, романтические обещания, документы, "
            "бюрократия"
        ),
    ),
)


ZODIAC_SIGN_PROFILE_ORDER = (
    "aries",
    "taurus",
    "gemini",
    "cancer",
    "leo",
    "virgo",
    "libra",
    "scorpio",
    "ophiuchus",
    "sagittarius",
    "capricorn",
    "aquarius",
    "pisces",
)


def build_prompt_variation_seed(
    *,
    sign_key: str,
    target_date: date,
    locale: str,
    forecast_type: str,
) -> str:
    return (
        f"{sign_key.strip().lower()}:"
        f"{target_date.isoformat()}:"
        f"{locale.strip().lower()}:"
        f"{forecast_type.strip().lower()}:"
        "prompt-variation-v1"
    )


def select_prompt_variation_profile(
    *,
    sign_key: str,
    target_date: date,
    locale: str,
    forecast_type: str,
) -> PromptVariationProfile:
    """
    Select a stable variation profile for one generation item.

    For known zodiac signs, each date gets a deterministic rotation over the
    profile list, so the daily package uses all profiles with minimal repeats.
    For unknown sign keys, fall back to a stable hash-based index.
    """
    normalized_sign_key = sign_key.strip().lower()
    profile_count = len(PROMPT_VARIATION_PROFILES)

    date_seed = f"{target_date.isoformat()}:{locale}:{forecast_type}:profile-order-v1"
    date_offset = _stable_index(date_seed, profile_count)

    try:
        sign_index = ZODIAC_SIGN_PROFILE_ORDER.index(normalized_sign_key)
    except ValueError:
        item_seed = build_prompt_variation_seed(
            sign_key=normalized_sign_key,
            target_date=target_date,
            locale=locale,
            forecast_type=forecast_type,
        )
        return PROMPT_VARIATION_PROFILES[_stable_index(item_seed, profile_count)]

    return PROMPT_VARIATION_PROFILES[(sign_index + date_offset) % profile_count]


def build_prompt_variation_variables(
    *,
    sign_key: str,
    target_date: date,
    locale: str,
    forecast_type: str,
) -> dict[str, str]:
    profile = select_prompt_variation_profile(
        sign_key=sign_key,
        target_date=target_date,
        locale=locale,
        forecast_type=forecast_type,
    )
    return profile.to_prompt_variables()


def build_prompt_variation_metadata(
    *,
    sign_key: str,
    target_date: date,
    locale: str,
    forecast_type: str,
) -> dict[str, Any]:
    profile = select_prompt_variation_profile(
        sign_key=sign_key,
        target_date=target_date,
        locale=locale,
        forecast_type=forecast_type,
    )

    return {
        "profile": profile.to_metadata(),
        "seed": build_prompt_variation_seed(
            sign_key=sign_key,
            target_date=target_date,
            locale=locale,
            forecast_type=forecast_type,
        ),
    }


def _stable_index(seed: str, modulo: int) -> int:
    if modulo < 1:
        raise ValueError("modulo must be greater than or equal to 1.")

    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % modulo