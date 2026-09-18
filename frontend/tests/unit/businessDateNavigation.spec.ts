import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Router } from 'vue-router'

vi.mock('../../src/views/Home.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../../src/views/HoroscopeView.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../../src/views/ArchiveMonth.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../../src/views/ArchiveForecast.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../../src/views/NotFound.vue', () => ({ default: { template: '<div />' } }))

let router: Router
let businessDate: typeof import('../../src/utils/businessDate')

beforeEach(async () => {
  vi.resetModules()
  vi.clearAllMocks()
  window.history.replaceState({}, '', '/')
  vi.stubGlobal('scrollTo', vi.fn())
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true, json: async () => ({ business_date: '2027-01-01', timezone: 'Europe/Kyiv' }),
  }))
  router = (await import('../../src/router/index')).default
  businessDate = await import('../../src/utils/businessDate')
})
afterEach(() => {
  router.options.history.destroy()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('business-date navigation', () => {
  it('redirects horoscope to the backend business day', async () => {
    await router.push('/horoscope')
    expect(router.currentRoute.value.fullPath).toBe('/horoscope/capricorn/2027-01-01')
  })

  it('redirects archive to the backend business year/month', async () => {
    await router.push('/archive')
    expect(router.currentRoute.value.fullPath).toBe('/archive/capricorn/2027/01')
  })

  it('keeps trailing-slash redirects and query/hash handling', async () => {
    await router.push('/horoscope/?view=test#forecast')
    expect(router.currentRoute.value.fullPath).toBe('/horoscope/capricorn/2027-01-01?view=test#forecast')
    await router.push('/archive/')
    expect(router.currentRoute.value.fullPath).toBe('/archive/capricorn/2027/01')
  })

  it.each([
    '/',
    '/horoscope/aries/2026-05-12',
    '/archive/aries/2026/05',
    '/archive/aries/2026/05/12',
    '/not-a-route',
    '/horoscope/invalid/not-a-date',
    '/archive/aries/not-a-year/05',
  ])('resolves %s without metadata, even on a cold load', async path => {
    const fetch = vi.fn().mockRejectedValue(new Error('offline'))
    vi.stubGlobal('fetch', fetch)
    expect(businessDate.businessContext.value).toBeNull()
    await router.push(path)
    expect(router.currentRoute.value.fullPath).toBe(path)
    expect(fetch).not.toHaveBeenCalled()
    expect(businessDate.businessContext.value).toBeNull()
  })

  it('does not require fresh metadata for an explicit date after initialization', async () => {
    await businessDate.refreshBusinessDate()
    const fetch = vi.fn().mockRejectedValue(new Error('offline'))
    vi.stubGlobal('fetch', fetch)
    await router.push('/horoscope/taurus/2026-05-13')
    expect(router.currentRoute.value.fullPath).toBe('/horoscope/taurus/2026-05-13')
    expect(fetch).not.toHaveBeenCalled()
  })

  it.each(['/horoscope', '/archive'])('does not guess a redirect date for %s when metadata is unavailable', async path => {
    await router.push('/horoscope/taurus/2026-05-13')
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
    await router.push(path)
    expect(router.currentRoute.value.fullPath).toBe('/horoscope/taurus/2026-05-13')
    expect(businessDate.businessDateError.value).not.toBe('')
    expect(businessDate.businessContext.value).toBeNull()
  })
})
