export interface Zodiac {
  key: string
  nameRu: string
  glyph: string
  start: string // MM-DD
  end: string // MM-DD
}

export const ZODIACS: Zodiac[] = [
  { key: 'capricorn', nameRu: 'Козерог', glyph: '♑︎', start: '12-22', end: '01-19' },
  { key: 'aquarius', nameRu: 'Водолей',  glyph: '♒︎', start: '01-20', end: '02-18' },
  { key: 'pisces',    nameRu: 'Рыбы',     glyph: '♓︎', start: '02-19', end: '03-20' },
  { key: 'aries',     nameRu: 'Овен',     glyph: '♈︎', start: '03-21', end: '04-19' },
  { key: 'taurus',    nameRu: 'Телец',   glyph: '♉︎', start: '04-20', end: '05-20' },
  { key: 'gemini',    nameRu: 'Близнецы', glyph: '♊︎', start: '05-21', end: '06-20' },
  { key: 'cancer',    nameRu: 'Рак',      glyph: '♋︎', start: '06-21', end: '07-22' },
  { key: 'leo',       nameRu: 'Лев',      glyph: '♌︎', start: '07-23', end: '08-22' },
  { key: 'virgo',     nameRu: 'Дева',     glyph: '♍︎', start: '08-23', end: '09-22' },
  { key: 'libra',     nameRu: 'Весы',   glyph: '♎︎', start: '09-23', end: '10-22' },
  { key: 'scorpio',   nameRu: 'Скорпион', glyph: '♏︎', start: '10-23', end: '11-21' },
  { key: 'ophiuchus', nameRu: 'Змееносец', glyph: '⛎', start: '11-30', end: '12-17' },
  { key: 'sagittarius', nameRu: 'Стрелец', glyph: '♐︎', start: '11-22', end: '12-21' },
]

// helpers ----------------------------------------------------------
export const findIndexByKey = (key: string) => ZODIACS.findIndex(z => z.key === key)
const mod = (i: number, len = ZODIACS.length) => ((i % len) + len) % len
export const nextKey = (key: string) => ZODIACS[mod(findIndexByKey(key) + 1)].key
export const prevKey = (key: string) => ZODIACS[mod(findIndexByKey(key) - 1)].key
export const formatRange = (s: string, e: string) => `${s.replace('-', '.')} – ${e.replace('-', '.')}`

// date utils (ISO YYYY‑MM‑DD)
export const todayIso = () => new Date().toISOString().slice(0, 10)
export const isoAddDays = (iso: string, d: number) => {
  const dt = new Date(iso)
  dt.setUTCDate(dt.getUTCDate() + d)
  return dt.toISOString().slice(0, 10)
}
export const prettifyDate = (iso: string) => {
  const today = todayIso()
  if (iso === today) return `Сегодня — ${human(iso)}`
  if (iso === isoAddDays(today, -1)) return `Вчера — ${human(iso)}`
  if (iso === isoAddDays(today, 1)) return `Завтра — ${human(iso)}`
  return human(iso)
}
const human = (iso: string) => new Date(iso).toLocaleDateString('ru-RU', { day:'numeric', month:'long', year:'numeric' })
export const maxForwardDate = isoAddDays(todayIso(), 1) // today + 1 == tommorow is the last forecast day
