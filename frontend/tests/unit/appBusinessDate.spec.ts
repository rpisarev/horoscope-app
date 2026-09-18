import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

beforeEach(() => {
  vi.resetModules()
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2040-05-01T12:00:00Z'))
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible')
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

const options = { global: { stubs: { RouterView: { template: '<div data-testid="view" />' } } } }
const meta = (day: string) => ({ ok: true, json: async () => ({ business_date: day, timezone: 'Europe/Kyiv' }) })

describe('application business date lifecycle', () => {
  it('renders route content while metadata loads and after an initial failure', async () => {
    const { default: App } = await import('../../src/App.vue')
    const fetch = vi.fn().mockRejectedValue(new Error('offline'))
    vi.stubGlobal('fetch', fetch)
    const wrapper = mount(App, options)
    expect(wrapper.find('[role="status"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="view"]').exists()).toBe(true)
    await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    expect(wrapper.get('button').text()).toBe('Повторить')
    expect(wrapper.find('[data-testid="view"]').exists()).toBe(true)
    // Cold convenience redirects may have been cancelled; retry explicitly after initial failure.
    await vi.advanceTimersByTimeAsync(60_000)
    expect(fetch).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('keeps content mounted through a metadata timeout and recovery', async () => {
    const { refreshBusinessDate } = await import('../../src/utils/businessDate')
    const { default: App } = await import('../../src/App.vue')
    const fetch = vi.fn().mockReturnValueOnce(new Promise(() => {})).mockResolvedValue(meta('2026-07-16'))
    vi.stubGlobal('fetch', fetch)
    const wrapper = mount(App, options)
    expect(wrapper.find('[data-testid="view"]').exists()).toBe(true)
    await vi.advanceTimersByTimeAsync(5_000)
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="view"]').exists()).toBe(true)
    await refreshBusinessDate()
    await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="view"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('refreshes long-lived visible pages and stops refreshing after unmount', async () => {
    const { refreshBusinessDate, todayIso } = await import('../../src/utils/businessDate')
    const { default: App } = await import('../../src/App.vue')
    const fetch = vi.fn().mockResolvedValueOnce(meta('2026-07-15')).mockResolvedValue(meta('2026-07-16'))
    vi.stubGlobal('fetch', fetch)
    await refreshBusinessDate()
    const wrapper = mount(App, options)
    await vi.advanceTimersByTimeAsync(60_000)
    expect(todayIso()).toBe('2026-07-16')
    expect(fetch).toHaveBeenCalledTimes(2)
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden')
    await vi.advanceTimersByTimeAsync(60_000)
    expect(fetch).toHaveBeenCalledTimes(2)
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible')
    document.dispatchEvent(new Event('visibilitychange'))
    await flushPromises()
    expect(fetch).toHaveBeenCalledTimes(3)
    wrapper.unmount()
    await vi.advanceTimersByTimeAsync(60_000)
    document.dispatchEvent(new Event('visibilitychange'))
    await flushPromises()
    expect(fetch).toHaveBeenCalledTimes(3)
  })
})
