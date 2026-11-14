interface ArchiveScope {
  sign: string
  locale: string
  type: string
}

export async function getArchiveYears({ sign, locale, type }: ArchiveScope): Promise<number[]> {
  const query = new URLSearchParams({ sign, locale, type })
  const response = await fetch(`/api/years?${query}`)
  if (!response.ok) throw new Error(`years status ${response.status}`)
  const payload = await response.json()
  if (!Array.isArray(payload)) throw new Error('Invalid archive years response')
  return payload.map(Number).filter(Number.isInteger)
}

function isCalendarDate(value: unknown): value is string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const timestamp = Date.parse(`${value}T00:00:00Z`)
  return Number.isFinite(timestamp) && new Date(timestamp).toISOString().slice(0, 10) === value
}

export async function getArchiveMonthAvailability({
  sign, year, month, locale, type,
}: ArchiveScope & { year: number; month: number }): Promise<ReadonlySet<string>> {
  const query = new URLSearchParams({ year: String(year), month: String(month), sign, locale, type })
  const response = await fetch(`/api/archive/month?${query}`)
  if (!response.ok) throw new Error(`archive month status ${response.status}`)
  const payload = await response.json()
  if (!Array.isArray(payload?.days)) throw new Error('Invalid archive month response')

  const dates = new Set<string>()
  for (const day of payload.days) {
    if (day?.has_forecast === true && isCalendarDate(day.date)) dates.add(day.date)
  }
  return dates
}
