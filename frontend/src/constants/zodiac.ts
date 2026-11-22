import { todayIso } from '../utils/businessDate'
import type { Locale } from '../utils/locale'
import { UI_TEXT } from '../utils/uiText'
export { todayIso } from '../utils/businessDate'

export interface Zodiac {
  key: string
  nameEn: string
  nameUk: string
  nameRu: string
  genitiveUk: string
  genitiveRu: string
  glyph: string
  start: string // MM-DD
  end: string // MM-DD
}

export interface HomeZodiacItem {
  name: string
  glyph: string
  range: string
  slug: string
}

export const ZODIACS: Zodiac[] = [
  { key: 'capricorn',   nameEn: 'Capricorn',   nameUk: 'Козеріг', nameRu: 'Козерог', genitiveUk: 'Козерога', genitiveRu: 'Козерога', glyph: '♑', start: '01-20', end: '02-16' },
  { key: 'aquarius',    nameEn: 'Aquarius',    nameUk: 'Водолій', nameRu: 'Водолей', genitiveUk: 'Водолія', genitiveRu: 'Водолея', glyph: '♒', start: '02-17', end: '03-11' },
  { key: 'pisces',      nameEn: 'Pisces',      nameUk: 'Риби', nameRu: 'Рыбы', genitiveUk: 'Риб', genitiveRu: 'Рыб', glyph: '♓', start: '03-12', end: '04-18' },
  { key: 'aries',       nameEn: 'Aries',       nameUk: 'Овен', nameRu: 'Овен', genitiveUk: 'Овна', genitiveRu: 'Овна', glyph: '♈', start: '04-19', end: '05-14' },
  { key: 'taurus',      nameEn: 'Taurus',      nameUk: 'Телець', nameRu: 'Телец', genitiveUk: 'Тельця', genitiveRu: 'Тельца', glyph: '♉', start: '05-15', end: '06-21' },
  { key: 'gemini',      nameEn: 'Gemini',      nameUk: 'Близнюки', nameRu: 'Близнецы', genitiveUk: 'Близнюків', genitiveRu: 'Близнецов', glyph: '♊', start: '06-22', end: '07-20' },
  { key: 'cancer',      nameEn: 'Cancer',      nameUk: 'Рак', nameRu: 'Рак', genitiveUk: 'Рака', genitiveRu: 'Рака', glyph: '♋', start: '07-21', end: '08-10' },
  { key: 'leo',         nameEn: 'Leo',         nameUk: 'Лев', nameRu: 'Лев', genitiveUk: 'Лева', genitiveRu: 'Льва', glyph: '♌', start: '08-11', end: '09-16' },
  { key: 'virgo',       nameEn: 'Virgo',       nameUk: 'Діва', nameRu: 'Дева', genitiveUk: 'Діви', genitiveRu: 'Девы', glyph: '♍', start: '09-17', end: '10-31' },
  { key: 'libra',       nameEn: 'Libra',       nameUk: 'Терези', nameRu: 'Весы', genitiveUk: 'Терезів', genitiveRu: 'Весов', glyph: '♎', start: '11-01', end: '11-23' },
  { key: 'scorpio',     nameEn: 'Scorpio',     nameUk: 'Скорпіон', nameRu: 'Скорпион', genitiveUk: 'Скорпіона', genitiveRu: 'Скорпиона', glyph: '♏', start: '11-24', end: '11-30' },
  { key: 'ophiuchus',   nameEn: 'Ophiuchus',   nameUk: 'Змієносець', nameRu: 'Змееносец', genitiveUk: 'Змієносця', genitiveRu: 'Змееносца', glyph: '⛎', start: '12-01', end: '12-18' },
  { key: 'sagittarius', nameEn: 'Sagittarius', nameUk: 'Стрілець', nameRu: 'Стрелец', genitiveUk: 'Стрільця', genitiveRu: 'Стрельца', glyph: '♐', start: '12-19', end: '01-19' },
]

// helpers ----------------------------------------------------------

export const getZodiacByKey = (key: string) => ZODIACS.find(z => z.key === key)

export const findIndexByKey = (key: string) =>
  ZODIACS.findIndex(z => z.key === key)

const mod = (i: number, len = ZODIACS.length) => ((i % len) + len) % len

export const nextKey = (key: string) => ZODIACS[mod(findIndexByKey(key) + 1)].key
export const prevKey = (key: string) => ZODIACS[mod(findIndexByKey(key) - 1)].key

export function zodiacName(sign: Zodiac, locale: Locale, genitive = false): string {
  if (locale === 'uk') return genitive ? sign.genitiveUk : sign.nameUk
  if (locale === 'ru') return genitive ? sign.genitiveRu : sign.nameRu
  return sign.nameEn
}

const rangeFormatters = new Map<Locale, Intl.DateTimeFormat>()

export function formatRange(start: string, end: string, locale: Locale = 'en'): string {
  let formatter = rangeFormatters.get(locale)
  if (!formatter) {
    formatter = new Intl.DateTimeFormat(locale, { month: 'short', day: 'numeric', timeZone: 'UTC' })
    rangeFormatters.set(locale, formatter)
  }
  return [start, end].map(date => formatter.format(new Date(`2000-${date}T00:00:00Z`))).join(' – ')
}

// Home page keeps the historical Aries -> Pisces order
const HOME_ORDER = [
  'aries',
  'taurus',
  'gemini',
  'cancer',
  'leo',
  'virgo',
  'libra',
  'scorpio',
  'ophiuchus',
  'sagittarius',
  'capricorn',
  'aquarius',
  'pisces',
]

export function homeZodiacs(locale: Locale, names?: ReadonlyMap<string, string>): HomeZodiacItem[] {
  return HOME_ORDER.map(key => {
    const zodiac = getZodiacByKey(key)!
    return {
      name: names?.get(key) ?? zodiacName(zodiac, locale),
      glyph: zodiac.glyph,
      range: formatRange(zodiac.start, zodiac.end, locale),
      slug: zodiac.key,
    }
  })
}

export const HOME_ZODIACS = homeZodiacs('en')

// date utils (ISO YYYY-MM-DD)

export const isoAddDays = (iso: string, d: number) => {
  const dt = new Date(iso)
  dt.setUTCDate(dt.getUTCDate() + d)
  return dt.toISOString().slice(0, 10)
}

export function formatDate(iso: string, locale: Locale): string {
  return new Date(iso).toLocaleDateString(locale, {
    day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC',
  })
}

export const prettifyDate = (iso: string, locale: Locale = 'en') => {
  const human = formatDate(iso, locale)
  const today = todayIso()
  if (!today) return human
  const text = UI_TEXT[locale]
  if (iso === today) return `${text.today} — ${human}`
  if (iso === isoAddDays(today, -1)) return `${text.yesterday} — ${human}`
  if (iso === isoAddDays(today, 1)) return `${text.tomorrow} — ${human}`
  return human
}

export const maxForwardDate = () => {
  const today = todayIso()
  return today ? isoAddDays(today, 1) : null
}
