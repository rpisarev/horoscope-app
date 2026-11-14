import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getForecast } from '../../src/api/forecast'

const scope = { sign: 'aries', date: '2026-09-28' }
const json = (payload: unknown, status = 200) => new Response(JSON.stringify(payload), {
  status, headers: { 'content-type': 'application/json' },
})

beforeEach(() => vi.stubGlobal('fetch', vi.fn()))
afterEach(() => vi.unstubAllGlobals())

describe('forecast API', () => {
  it.each([
    ['JSON string', 'Published text', 'Published text'],
    ['text field', { text: 'Text' }, 'Text'],
    ['forecast alias', { forecast: 'Alias' }, 'Alias'],
    ['text precedence', { text: 'Text', forecast: 'Alias' }, 'Text'],
    ['string alias after non-string text', { text: null, forecast: 'Alias' }, 'Alias'],
    ['empty JSON string', '', ''],
    ['empty text precedence', { text: '', forecast: 'Alias' }, ''],
    ['empty alias', { forecast: '' }, ''],
  ])('accepts %s', async (_, payload, text) => {
    vi.mocked(fetch).mockResolvedValueOnce(json(payload))
    await expect(getForecast(scope)).resolves.toEqual({ kind: 'published', text })
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(fetch).toHaveBeenCalledWith('/api/forecast?sign=aries&date=2026-09-28')
  })

  it.each(['Plain text', ''])('preserves non-JSON text %j', async text => {
    vi.mocked(fetch).mockResolvedValueOnce(new Response(text, { headers: { 'content-type': 'text/plain' } }))
    await expect(getForecast(scope)).resolves.toEqual({ kind: 'published', text })
  })

  it('recognizes only the unpublished 404 contract', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(json({ error: 'forecast_not_published' }, 404))
    await expect(getForecast(scope)).resolves.toEqual({ kind: 'not-published' })
  })

  it.each([
    [404, { error: 'other' }],
    [500, { error: 'forecast_not_published' }],
  ])('rejects HTTP %s outside the unpublished contract', async (status, payload) => {
    vi.mocked(fetch).mockResolvedValueOnce(json(payload, status))
    await expect(getForecast(scope)).rejects.toThrow(`forecast status ${status}`)
  })

  it('propagates network failure', async () => {
    const error = new Error('offline')
    vi.mocked(fetch).mockRejectedValueOnce(error)
    await expect(getForecast(scope)).rejects.toBe(error)
  })

  it.each([200, 404])('rejects malformed JSON at HTTP %s', async status => {
    vi.mocked(fetch).mockResolvedValueOnce(new Response('{', {
      status, headers: { 'content-type': 'application/json' },
    }))
    await expect(getForecast(scope)).rejects.toBeInstanceOf(SyntaxError)
  })

  it.each([null, {}, [], 42, { text: 42 }, { forecast: null }, { error: 'forecast_not_published' }])(
    'rejects malformed successful shape %j', async payload => {
      vi.mocked(fetch).mockResolvedValueOnce(json(payload))
      await expect(getForecast(scope)).rejects.toThrow('Invalid forecast response')
    }
  )
})
