import { getZodiacByKey } from '../constants/zodiac'

export type RouteErrorCode =
  | 'SIGN_NOT_FOUND'
  | 'HOROSCOPE_DATE_NOT_FOUND'
  | 'ARCHIVE_YEAR_NOT_FOUND'
  | 'MONTH_NOT_FOUND'
  | 'DAY_NOT_FOUND'
  | 'PAGE_NOT_FOUND'

export interface RouteValidationSuccess<TParams> {
  ok: true
  code: null
  message: null
  params: TParams
}

export interface RouteValidationFailure {
  ok: false
  code: RouteErrorCode
  message: string
  params: null
}

export type RouteValidationResult<TParams> =
  | RouteValidationSuccess<TParams>
  | RouteValidationFailure

export const ROUTE_ERROR_MESSAGES: Record<RouteErrorCode, string> = {
  SIGN_NOT_FOUND: 'Такой знак не найден',
  HOROSCOPE_DATE_NOT_FOUND: 'Такой день не найден',
  ARCHIVE_YEAR_NOT_FOUND: 'Архив за этот год недоступен',
  MONTH_NOT_FOUND: 'Такой месяц не найден',
  DAY_NOT_FOUND: 'Такой день не найден',
  PAGE_NOT_FOUND: 'Страница не найдена',
}

function success<TParams>(params: TParams): RouteValidationSuccess<TParams> {
  return {
    ok: true,
    code: null,
    message: null,
    params,
  }
}

function failure(code: RouteErrorCode): RouteValidationFailure {
  return {
    ok: false,
    code,
    message: ROUTE_ERROR_MESSAGES[code],
    params: null,
  }
}

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

export function validateHoroscopeRoute(
  params: Record<string, unknown>
): RouteValidationResult<{
  sign: string
  day: string
}> {
  const sign = routeParamToString(params.sign)
  const day = routeParamToString(params.day)

  if (!isKnownSign(sign)) {
    return failure('SIGN_NOT_FOUND')
  }

  if (!isRealIsoDate(day)) {
    return failure('HOROSCOPE_DATE_NOT_FOUND')
  }

  return success({
    sign,
    day,
  })
}

export function validateArchiveMonthRoute(
  params: Record<string, unknown>,
  years: number[] = [],
  isYearsLoaded = false
): RouteValidationResult<{
  sign: string
  year: number
  month: number
}> {
  const sign = routeParamToString(params.sign)
  const year = parseYearParam(params.year)
  const month = parseMonthParam(params.month)

  if (!isKnownSign(sign)) {
    return failure('SIGN_NOT_FOUND')
  }

  if (year === null) {
    return failure('ARCHIVE_YEAR_NOT_FOUND')
  }

  if (month === null) {
    return failure('MONTH_NOT_FOUND')
  }

  if (isYearsLoaded && years.length > 0 && !years.includes(year)) {
    return failure('ARCHIVE_YEAR_NOT_FOUND')
  }

  return success({
    sign,
    year,
    month,
  })
}

export function validateArchiveForecastRoute(
  params: Record<string, unknown>,
  years: number[] = [],
  isYearsLoaded = false
): RouteValidationResult<{
  sign: string
  year: number
  month: number
  day: number
}> {
  const sign = routeParamToString(params.sign)
  const year = parseYearParam(params.year)
  const month = parseMonthParam(params.month)
  const day = parseArchiveDayParam(params.day)

  if (!isKnownSign(sign)) {
    return failure('SIGN_NOT_FOUND')
  }

  if (year === null) {
    return failure('ARCHIVE_YEAR_NOT_FOUND')
  }

  if (month === null) {
    return failure('MONTH_NOT_FOUND')
  }

  if (isYearsLoaded && years.length > 0 && !years.includes(year)) {
    return failure('ARCHIVE_YEAR_NOT_FOUND')
  }

  if (day === null || day < 1 || day > daysInMonth(year, month)) {
    return failure('DAY_NOT_FOUND')
  }

  return success({
    sign,
    year,
    month,
    day,
  })
}

export function getPageNotFoundError(): RouteValidationFailure {
  return failure('PAGE_NOT_FOUND')
}