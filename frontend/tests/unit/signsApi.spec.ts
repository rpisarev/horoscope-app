import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getSignMetadata } from '../../src/api/signs'

const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status })
beforeEach(() => vi.stubGlobal('fetch', vi.fn()))
afterEach(() => vi.unstubAllGlobals())

describe('localized sign metadata', () => {
  it('uses active localized names, skipping malformed entries and legacy fallback labels', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(json({ locale: 'uk', items: [
      { key: 'taurus', name: 'Телець', is_active: true },
      { key: 'gemini', name: 'Близнюки', is_active: true, name_locale: 'uk' },
      { key: 'libra', name: 'Весы', is_active: true, name_locale: 'ru' },
      { key: 'virgo', name: 'Діва', is_active: false },
      { key: 'pisces', name: 'Риби', is_active: 'true' },
      { key: 'scorpio', name: ' ', is_active: true },
      { key: null, name: 'Рак', is_active: true }, null,
    ] }))
    await expect(getSignMetadata('uk')).resolves.toEqual(new Map([['taurus', 'Телець'], ['gemini', 'Близнюки']]))
    expect(fetch).toHaveBeenCalledExactlyOnceWith('/api/signs/meta?locale=uk')
  })

  it.each(['en', 'uk', 'ru'] as const)('requests locale %s even for an empty list', async locale => {
    vi.mocked(fetch).mockResolvedValueOnce(json({ locale, items: [] }))
    await expect(getSignMetadata(locale)).resolves.toEqual(new Map())
    expect(fetch).toHaveBeenCalledExactlyOnceWith(`/api/signs/meta?locale=${locale}`)
  })

  it.each([null, {}, { items: [] }, { locale: 'ru', items: [] }, { locale: 'uk', items: {} }])(
    'rejects a missing or inconsistent edition in %j', async data => {
      vi.mocked(fetch).mockResolvedValueOnce(json(data))
      await expect(getSignMetadata('uk')).rejects.toThrow('Invalid sign metadata response')
    },
  )

  it('rejects errors without requesting a different language', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(json({}, 503))
    await expect(getSignMetadata('en')).rejects.toThrow('sign metadata status 503')
    expect(fetch).toHaveBeenCalledTimes(1)
  })
})
