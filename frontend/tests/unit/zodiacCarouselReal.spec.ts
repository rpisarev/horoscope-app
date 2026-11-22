import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Swiper as SwiperType } from 'swiper'
import ZodiacCarousel from '../../src/components/ZodiacCarousel.vue'
import { ZODIACS, findIndexByKey } from '../../src/constants/zodiac'

const cleanups: Array<() => void> = []

beforeEach(() => {
  vi.useFakeTimers()
  // jsdom has no layout. Supply only geometry and media queries; Swiper's Vue
  // wrapper, loop implementation, events and destruction are the real package.
  vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(320)
  vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(320)
  vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(100)
  vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(100)
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: Number(query.match(/\d+/)?.[0] ?? 0) <= 1024,
    addEventListener: vi.fn(), removeEventListener: vi.fn(),
  }))
})

afterEach(() => {
  cleanups.splice(0).reverse().forEach(cleanup => cleanup())
  vi.clearAllTimers()
  vi.useRealTimers()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

async function settle() {
  await vi.advanceTimersByTimeAsync(100)
  await flushPromises()
}

async function mountReal(sign: string) {
  const wrapper = mount(ZodiacCarousel, { props: { modelValue: sign }, attachTo: document.body })
  cleanups.push(() => wrapper.unmount())
  await settle()
  const swiper = (wrapper.get('.swiper').element as HTMLElement & { swiper: SwiperType }).swiper
  // jsdom does not dispatch CSS transitionend; zero duration isolates index and
  // event behavior from an animation it cannot render.
  swiper.params.speed = 0
  return { wrapper, swiper }
}

describe('ZodiacCarousel with real Swiper in jsdom (not browser smoke)', () => {
  it.each(['capricorn', 'aries', 'ophiuchus', 'sagittarius'])('initializes %s with the Vue export', async sign => {
    const { wrapper, swiper } = await mountReal(sign)
    expect(swiper.initialized).toBe(true)
    expect(swiper.params.loop).toBe(true)
    expect(swiper.realIndex).toBe(findIndexByKey(sign))
    expect(wrapper.get('.opacity-100').text()).toContain(ZODIACS[findIndexByKey(sign)].nameEn)
  })

  it('handles real arrow clicks and loop edges', async () => {
    const { wrapper, swiper } = await mountReal('capricorn')
    await wrapper.get('button[aria-label="Previous sign"]').trigger('click')
    await settle()
    expect(swiper.realIndex).toBe(ZODIACS.length - 1)
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['sagittarius'])
    await wrapper.get('button[aria-label="Next sign"]').trigger('click')
    await settle()
    expect(swiper.realIndex).toBe(0)
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['capricorn'])
  })

  it('settles repeated parent sign changes through real slideToLoop', async () => {
    const { wrapper, swiper } = await mountReal('aries')
    for (const sign of ['ophiuchus', 'capricorn', 'leo', 'sagittarius', 'aries']) {
      await wrapper.setProps({ modelValue: sign })
      await settle()
      expect(swiper.realIndex).toBe(findIndexByKey(sign))
      expect(wrapper.get('.opacity-100').text()).toContain(ZODIACS[findIndexByKey(sign)].nameEn)
      expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([sign])
    }
  })

  it('destroys the real instance on unmount and can mount repeatedly', async () => {
    for (const sign of ['aries', 'leo', 'ophiuchus']) {
      const { wrapper, swiper } = await mountReal(sign)
      wrapper.unmount()
      cleanups.pop()
      await settle()
      expect(swiper.destroyed).toBe(true)
      expect(document.querySelector('.swiper')).toBeNull()
    }
  })
})
