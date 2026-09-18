import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest'

let DaySlider: typeof import('../../src/components/DaySlider.vue')['default']
let businessDate: typeof import('../../src/utils/businessDate')
let dates: typeof import('../../src/constants/zodiac')

beforeEach(async () => {
  vi.resetModules()
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2040-05-01T12:00:00Z'))
  DaySlider = (await import('../../src/components/DaySlider.vue')).default
  businessDate = await import('../../src/utils/businessDate')
  dates = await import('../../src/constants/zodiac')
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

async function setServerDate(day: string) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true, json: async () => ({ business_date: day, timezone: 'Europe/Kyiv' }),
  }))
  await businessDate.refreshBusinessDate()
}

describe('DaySlider business date', () => {
  it('shows an absolute date and disables forward navigation until the business date loads', async () => {
    const wrapper = mount(DaySlider, { props: { modelValue: '2026-07-16' } })
    expect(wrapper.text()).toBe('16 июля 2026 г.')
    const next = wrapper.get('button[aria-label="Next day"]')
    expect(next.attributes('disabled')).toBeDefined()
    await next.trigger('click')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    await setServerDate('2026-07-16')
    await flushPromises()
    expect(wrapper.text()).toContain('Сегодня')
    expect(next.attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('labels dates relative to the server, regardless of the browser clock', async () => {
    await setServerDate('2026-01-01')
    const wrapper = mount(DaySlider, { props: { modelValue: '2026-01-01' } })
    expect(wrapper.text()).toContain('Сегодня — 1 января 2026 г.')
    expect(dates.prettifyDate('2025-12-31')).toContain('Вчера')
    expect(dates.prettifyDate('2026-01-02')).toContain('Завтра')
    expect(dates.isoAddDays('2026-01-01', -1)).toBe('2025-12-31')
    wrapper.unmount()
  })

  it('updates labels and tomorrow limit after the next server date is loaded', async () => {
    await setServerDate('2026-07-15')
    const wrapper = mount(DaySlider, { props: { modelValue: '2026-07-16' } })
    const next = wrapper.get('button[aria-label="Next day"]')
    expect(wrapper.text()).toContain('Завтра')
    expect(next.attributes('disabled')).toBeDefined()
    await setServerDate('2026-07-16')
    await flushPromises()
    expect(wrapper.text()).toContain('Сегодня')
    expect(next.attributes('disabled')).toBeUndefined()
    await next.trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([['2026-07-17']])
    wrapper.unmount()
  })
})
