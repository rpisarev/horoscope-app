export type ForecastResult =
  | { kind: 'published'; text: string }
  | { kind: 'not-published' }

export async function getForecast({ sign, date }: { sign: string; date: string }): Promise<ForecastResult> {
  const query = new URLSearchParams({ sign, date })
  const response = await fetch(`/api/forecast?${query}`)

  if (response.status === 404) {
    const payload = await response.json()
    if (payload?.error === 'forecast_not_published') return { kind: 'not-published' }
  }
  if (!response.ok) throw new Error(`forecast status ${response.status}`)

  const contentType = response.headers.get('content-type') ?? ''
  if (!contentType.includes('application/json')) {
    return { kind: 'published', text: await response.text() }
  }

  const payload = await response.json()
  // Empty strings are valid content; a missing compatible string is a contract failure.
  if (typeof payload === 'string') return { kind: 'published', text: payload }
  if (typeof payload?.text === 'string') return { kind: 'published', text: payload.text }
  if (typeof payload?.forecast === 'string') return { kind: 'published', text: payload.forecast }
  throw new Error('Invalid forecast response')
}
