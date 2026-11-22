import type { Locale } from '../utils/locale'

export type ForecastResult =
  | { kind: 'published'; text: string }
  | { kind: 'not-published' }

interface ForecastScope {
  sign: string
  date: string
  locale?: Locale
}

async function readForecastJson(response: Response, locale: Locale) {
  const payload = await response.json()
  if (payload?.locale !== undefined && payload.locale !== locale) throw new Error('Unexpected forecast locale')
  return payload
}

export async function getForecast({ sign, date, locale = 'en' }: ForecastScope): Promise<ForecastResult> {
  const query = new URLSearchParams({ sign, date, locale })
  const response = await fetch(`/api/forecast?${query}`)

  if (response.status === 404) {
    const payload = await readForecastJson(response, locale)
    if (payload?.error === 'forecast_not_published') return { kind: 'not-published' }
  }
  if (!response.ok) throw new Error(`forecast status ${response.status}`)

  const contentType = response.headers.get('content-type') ?? ''
  if (!contentType.includes('application/json')) {
    return { kind: 'published', text: await response.text() }
  }

  const payload = await readForecastJson(response, locale)
  // Empty strings are valid content; a missing compatible string is a contract failure.
  if (typeof payload === 'string') return { kind: 'published', text: payload }
  if (typeof payload?.text === 'string') return { kind: 'published', text: payload.text }
  if (typeof payload?.forecast === 'string') return { kind: 'published', text: payload.forecast }
  throw new Error('Invalid forecast response')
}
