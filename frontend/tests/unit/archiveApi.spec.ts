import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getArchiveYears, getArchiveMonthAvailability, getLatestPublishedDate } from '../../src/api/archive'

const scope = { sign: 'gemini', locale: 'ru', type: 'daily' } as const
const monthScope = { ...scope, year: 2026, month: 6 }
const json = (payload: unknown, status = 200) => new Response(JSON.stringify(payload), { status })

beforeEach(() => vi.stubGlobal('fetch', vi.fn()))
afterEach(() => vi.unstubAllGlobals())

describe('archive years API', () => {
  it('preserves integer conversion and filtering', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(json([2024, '2025', ' 2026 ', 'invalid', 2026.5]))
    await expect(getArchiveYears(scope)).resolves.toEqual([2024, 2025, 2026])
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(fetch).toHaveBeenCalledWith('/api/years?sign=gemini&locale=ru&type=daily')
  })

  it('accepts an empty array', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(json([]))
    await expect(getArchiveYears(scope)).resolves.toEqual([])
  })

  it.each([null, {}, { years: [2026] }, '2026', 2026])('rejects non-array payload %j', async payload => {
    vi.mocked(fetch).mockResolvedValueOnce(json(payload))
    await expect(getArchiveYears(scope)).rejects.toThrow('Invalid archive years response')
  })
})

describe('archive month API', () => {
  it.each([getArchiveMonthAvailability, getLatestPublishedDate])('rejects metadata from a different edition', async read => {
    vi.mocked(fetch).mockResolvedValueOnce(json({ locale: 'en', days: [], latest_published_date: '2026-06-26' }))
    await expect(read(monthScope)).rejects.toThrow('Unexpected archive month locale')
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('returns only strict published flags with real ISO dates, ignoring malformed entries and aggregates', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(json({ days: [
      { date: '2026-06-06', has_forecast: true },
      { date: '2026-06-06', has_forecast: true },
      { date: '2026-06-26', has_forecast: true, forecast_count: 0 },
      { date: '2026-06-10', has_forecast: false, has_full_coverage: true, forecast_count: 13 },
      { date: '2026-06-11', has_forecast: 'true' },
      { date: '2026-06-12', has_forecast: 1 },
      { date: '2026-06-13' },
      { date: '2026-02-30', has_forecast: true },
      { date: 'not-a-date', has_forecast: true },
      { date: '2026-6-14', has_forecast: true },
      { date: 26, has_forecast: true },
      { has_forecast: true }, null, {}, '2026-06-15',
    ] }))
    await expect(getArchiveMonthAvailability(monthScope)).resolves.toEqual(new Set(['2026-06-06', '2026-06-26']))
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(fetch).toHaveBeenCalledWith('/api/archive/month?year=2026&month=6&sign=gemini&locale=ru&type=daily')
  })

  it('accepts empty availability', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(json({ days: [] }))
    await expect(getArchiveMonthAvailability(monthScope)).resolves.toEqual(new Set())
  })

  it.each([null, {}, [], { days: null }, { days: {} }])('rejects malformed envelope %j', async payload => {
    vi.mocked(fetch).mockResolvedValueOnce(json(payload))
    await expect(getArchiveMonthAvailability(monthScope)).rejects.toThrow('Invalid archive month response')
  })
})

describe.each([
  ['years', () => getArchiveYears(scope), 'years status 500'],
  ['month', () => getArchiveMonthAvailability(monthScope), 'archive month status 500'],
  ['latest', () => getLatestPublishedDate(monthScope), 'archive month status 500'],
] as const)('archive %s failures', (_, request, message) => {
  it('rejects HTTP failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(json({}, 500))
    await expect(request()).rejects.toThrow(message)
  })

  it('propagates network failure', async () => {
    const error = new Error('offline')
    vi.mocked(fetch).mockRejectedValueOnce(error)
    await expect(request()).rejects.toBe(error)
  })

  it('rejects malformed JSON', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(new Response('{'))
    await expect(request()).rejects.toBeInstanceOf(SyntaxError)
  })
})

describe('latest published date', () => {
  it.each([null, '2024-02-29', '2027-01-01'])('reads the scoped all-time result %s', async date => {
    vi.mocked(fetch).mockResolvedValueOnce(json({
      days: [{ date: '2026-06-10', has_forecast: true }], latest_published_date: date,
    }))
    await expect(getLatestPublishedDate(monthScope)).resolves.toBe(date)
    expect(fetch).toHaveBeenCalledExactlyOnceWith('/api/archive/month?year=2026&month=6&sign=gemini&locale=ru&type=daily&include_latest=1')
  })

  it.each([{}, null, { latest_published_date: '2026-02-29' }, { latest_published_date: '0000-01-01' }, { latest_published_date: 20260701 }])(
    'rejects a missing or malformed field in %j', async payload => {
      vi.mocked(fetch).mockResolvedValueOnce(json(payload))
      await expect(getLatestPublishedDate(monthScope)).rejects.toThrow('Invalid latest published date')
    },
  )
})
