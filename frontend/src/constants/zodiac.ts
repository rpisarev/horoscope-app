export interface Zodiac {
  key: string
  nameRu: string
  glyph: string
  start: string // MM-DD
  end: string // MM-DD
}

export const ZODIACS: Zodiac[] = [
  { key: 'capricorn', nameRu: 'Козерог', glyph: '♑︎', start: '01-20', end: '02-16' },
  { key: 'aquarius', nameRu: 'Водолей',  glyph: '♒︎', start: '02-17', end: '03-11' },
  { key: 'pisces',    nameRu: 'Рыбы',     glyph: '♓︎', start: '03-12', end: '04-18' },
  { key: 'aries',     nameRu: 'Овен',     glyph: '♈︎', start: '04-19', end: '05-14' },
  { key: 'taurus',    nameRu: 'Телец',   glyph: '♉︎', start: '05-15', end: '06-21' },
  { key: 'gemini',    nameRu: 'Близнецы', glyph: '♊︎', start: '06-22', end: '07-20' },
  { key: 'cancer',    nameRu: 'Рак',      glyph: '♋︎', start: '07-21', end: '08-10' },
  { key: 'leo',       nameRu: 'Лев',      glyph: '♌︎', start: '08-11', end: '09-16' },
  { key: 'virgo',     nameRu: 'Дева',     glyph: '♍︎', start: '09-17', end: '10-31' },
  { key: 'libra',     nameRu: 'Весы',   glyph: '♎︎', start: '11-01', end: '11-23' },
  { key: 'scorpio',   nameRu: 'Скорпион', glyph: '♏︎', start: '11-24', end: '11-30' },
  { key: 'ophiuchus', nameRu: 'Змееносец', glyph: '⛎', start: '12-01', end: '12-18' },
  { key: 'sagittarius', nameRu: 'Стрелец', glyph: '♐︎', start: '12-19', end: '01-19' },
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
