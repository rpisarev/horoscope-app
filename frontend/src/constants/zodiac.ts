export interface Zodiac {
  key: string
  nameEn: string
  nameRu: string
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
  { key: 'capricorn',  nameEn: 'Capricorn',  nameRu: 'Козерог',    glyph: '♑︎', start: '01-20', end: '02-16' },
  { key: 'aquarius',   nameEn: 'Aquarius',   nameRu: 'Водолей',    glyph: '♒︎', start: '02-17', end: '03-11' },
  { key: 'pisces',     nameEn: 'Pisces',     nameRu: 'Рыбы',       glyph: '♓︎', start: '03-12', end: '04-18' },
  { key: 'aries',      nameEn: 'Aries',      nameRu: 'Овен',       glyph: '♈︎', start: '04-19', end: '05-14' },
  { key: 'taurus',     nameEn: 'Taurus',     nameRu: 'Телец',      glyph: '♉︎', start: '05-15', end: '06-21' },
  { key: 'gemini',     nameEn: 'Gemini',     nameRu: 'Близнецы',   glyph: '♊︎', start: '06-22', end: '07-20' },
  { key: 'cancer',     nameEn: 'Cancer',     nameRu: 'Рак',        glyph: '♋︎', start: '07-21', end: '08-10' },
  { key: 'leo',        nameEn: 'Leo',        nameRu: 'Лев',        glyph: '♌︎', start: '08-11', end: '09-16' },
  { key: 'virgo',      nameEn: 'Virgo',      nameRu: 'Дева',       glyph: '♍︎', start: '09-17', end: '10-31' },
  { key: 'libra',      nameEn: 'Libra',      nameRu: 'Весы',       glyph: '♎︎', start: '11-01', end: '11-23' },
  { key: 'scorpio',    nameEn: 'Scorpio',    nameRu: 'Скорпион',   glyph: '♏︎', start: '11-24', end: '11-30' },
  { key: 'ophiuchus',  nameEn: 'Ophiuchus',  nameRu: 'Змееносец',  glyph: '⛎',  start: '12-01', end: '12-18' },
  { key: 'sagittarius',nameEn: 'Sagittarius',nameRu: 'Стрелец',    glyph: '♐︎', start: '12-19', end: '01-19' },
]

// helpers ----------------------------------------------------------

export const getZodiacByKey = (key: string) => ZODIACS.find(z => z.key === key)

export const findIndexByKey = (key: string) =>
  ZODIACS.findIndex(z => z.key === key)

const mod = (i: number, len = ZODIACS.length) => ((i % len) + len) % len

export const nextKey = (key: string) => ZODIACS[mod(findIndexByKey(key) + 1)].key
export const prevKey = (key: string) => ZODIACS[mod(findIndexByKey(key) - 1)].key

export const formatRange = (s: string, e: string) =>
  `${s.replace('-', '.')} – ${e.replace('-', '.')}`

const EN_MONTHS: Record<string, string> = {
  '01': 'Jan',
  '02': 'Feb',
  '03': 'Mar',
  '04': 'Apr',
  '05': 'May',
  '06': 'Jun',
  '07': 'Jul',
  '08': 'Aug',
  '09': 'Sep',
  '10': 'Oct',
  '11': 'Nov',
  '12': 'Dec',
}

const formatEnDate = (mmdd: string) => {
  const [month, day] = mmdd.split('-')
  return `${day} ${EN_MONTHS[month]}`
}

export const formatRangeEn = (s: string, e: string) =>
  `${formatEnDate(s)} – ${formatEnDate(e)}`

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

export const HOME_ZODIACS: HomeZodiacItem[] = HOME_ORDER
  .map(key => getZodiacByKey(key))
  .filter((z): z is Zodiac => Boolean(z))
  .map(z => ({
    name: z.nameEn,
    glyph: z.glyph,
    range: formatRangeEn(z.start, z.end),
    slug: z.key,
  }))

// date utils (ISO YYYY-MM-DD)

export const todayIso = () => new Date().toISOString().slice(0, 10)

export const isoAddDays = (iso: string, d: number) => {
  const dt = new Date(iso)
  dt.setUTCDate(dt.getUTCDate() + d)
  return dt.toISOString().slice(0, 10)
}

const human = (iso: string) =>
  new Date(iso).toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })

export const prettifyDate = (iso: string) => {
  const today = todayIso()

  if (iso === today) return `Сегодня — ${human(iso)}`
  if (iso === isoAddDays(today, -1)) return `Вчера — ${human(iso)}`
  if (iso === isoAddDays(today, 1)) return `Завтра — ${human(iso)}`

  return human(iso)
}

export const maxForwardDate = isoAddDays(todayIso(), 1)