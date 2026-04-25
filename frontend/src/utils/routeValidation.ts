import { getZodiacByKey } from '../constants/zodiac'

export function routeParamToString(value: unknown): string {
  if (Array.isArray(value)) {
    return String(value[0] ?? '')
  }

  return String(value ?? '')
}

export function isKnownSign(value: unknown): boolean {
  const sign = routeParamToString(value)

  return Boolean(getZodiacByKey(sign))
}

export function parseYearParam(value: unknown): number | null {
  const text = routeParamToString(value)

  if (!/^\d{4}$/.test(text)) {
    return null
  }

  const year = Number(text)

  return Number.isSafeInteger(year) ? year : null
}

export function parseMonthParam(value: unknown): number | null {
  const text = routeParamToString(value)

  if (!/^\d{1,2}$/.test(text)) {
    return null
  }

  const month = Number(text)

  return month >= 1 && month <= 12 ? month : null
}

export function parseArchiveDayParam(value: unknown): number | null {
  const text = routeParamToString(value)

  if (!/^-?\d+$/.test(text)) {
    return null
  }

  const day = Number(text)

  return Number.isSafeInteger(day) ? day : null
}

export function isRealIsoDate(value: unknown): boolean {
  const text = routeParamToString(value)
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text)

  if (!match) {
    return false
  }

  const year = Number(match[1])
  const month = Number(match[2])
  const day = Number(match[3])

  const date = new Date(Date.UTC(year, month - 1, day))

  return (
    date.getUTCFullYear() === year &&
    date.getUTCMonth() === month - 1 &&
    date.getUTCDate() === day
  )
}

export function daysInMonth(year: number, month: number): number {
  return new Date(Date.UTC(year, month, 0)).getUTCDate()
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max)
}

export function clampArchiveDay(year: number, month: number, day: number): number {
  return clamp(day, 1, daysInMonth(year, month))
}

export function pad2(value: number): string {
  return String(value).padStart(2, '0')
}