import { flushPromises, mount } from '@vue/test-utils'
import { computed, defineComponent, h, onMounted } from 'vue'
import { createMemoryHistory, createRouter, RouterView, useRoute, useRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ZodiacCarousel from '../../src/components/ZodiacCarousel.vue'
import { ZODIACS, findIndexByKey } from '../../src/constants/zodiac'

const cleanups: Array<() => void> = []
afterEach(() => {
  cleanups.splice(0).reverse().forEach(cleanup => cleanup())
})

// Deliberately synchronous test double: checks the component boundary, not
// Swiper's DOM layout, gesture handling or asynchronous loop event ordering.
function swiperDouble() {
  let dispatch: (event: string, value: unknown) => void
  const driver = {
    realIndex: 0,
    slideToLoop: vi.fn((index: number) => {
      driver.realIndex = index
      dispatch('slideChange', driver)
    }),
    slidePrev: vi.fn(() => driver.slideToLoop((driver.realIndex + ZODIACS.length - 1) % ZODIACS.length)),
    slideNext: vi.fn(() => driver.slideToLoop((driver.realIndex + 1) % ZODIACS.length)),
  }
  const Swiper = defineComponent({
    props: ['initialSlide', 'loop', 'centeredSlides', 'breakpoints'],
    emits: ['swiper', 'slideChange'],
    setup(props, { slots, emit }) {
      dispatch = emit
      driver.realIndex = props.initialSlide
      onMounted(() => emit('swiper', driver))
      return () => h('div', { 'data-swiper-double': '' }, slots.default?.())
    },
  })
  const SwiperSlide = defineComponent({
    setup(_, { slots }) {
      return () => h('div', { 'data-slide-double': '' }, slots.default?.())
    },
  })
  return {
    driver,
    stubs: { Swiper, SwiperSlide },
    slide(index: number) {
      driver.realIndex = index
      dispatch('slideChange', driver)
    },
  }
}

function mountCarousel(sign = 'aries') {
  const swiper = swiperDouble()
  const errors = vi.fn()
  const wrapper = mount(ZodiacCarousel, {
    props: { modelValue: sign },
    attachTo: document.body,
    global: { stubs: swiper.stubs, config: { errorHandler: errors } },
  })
  cleanups.push(() => wrapper.unmount())
  return { wrapper, errors, ...swiper }
}

function activeText(wrapper: ReturnType<typeof mount>) {
  return wrapper.get('.opacity-100').text()
}

describe('ZodiacCarousel component contract (Swiper double)', () => {
  it.each(ZODIACS.map(z => [z.key, z.nameRu]))('selects the initial %s sign', (key, name) => {
    const { wrapper, driver } = mountCarousel(key)
    expect(driver.realIndex).toBe(findIndexByKey(key))
    expect(activeText(wrapper)).toContain(name)
    expect(wrapper.findAll('[data-slide-double]')).toHaveLength(ZODIACS.length)
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })

  it('keeps loop, centered one-slide breakpoints and native labeled arrow buttons', () => {
    const { wrapper } = mountCarousel()
    const props = wrapper.getComponent('[data-swiper-double]').props()
    expect(props.loop).toBe(true)
    expect(props.centeredSlides).toBe(true)
    expect(props.breakpoints).toEqual({ 0: { slidesPerView: 1 }, 768: { slidesPerView: 1 } })
    for (const label of ['Prev sign', 'Next sign']) {
      const button = wrapper.get(`button[aria-label="${label}"]`)
      expect(button.attributes('disabled')).toBeUndefined()
      expect(button.attributes('tabindex')).not.toBe('-1')
    }
  })

  it('maps slide events by realIndex, including both loop endpoints', async () => {
    const { wrapper, slide } = mountCarousel()
    for (const index of [ZODIACS.length - 1, 0, 1]) {
      slide(index)
      await flushPromises()
      expect(activeText(wrapper)).toContain(ZODIACS[index].nameRu)
      expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([ZODIACS[index].key])
    }
  })

  it('delegates mouse activation to Swiper and wraps in each direction', async () => {
    const { wrapper, driver } = mountCarousel('capricorn')
    await wrapper.get('button[aria-label="Prev sign"]').trigger('click')
    expect(driver.slidePrev).toHaveBeenCalledOnce()
    expect(activeText(wrapper)).toContain(ZODIACS.at(-1)!.nameRu)
    await wrapper.get('button[aria-label="Next sign"]').trigger('click')
    expect(driver.slideNext).toHaveBeenCalledOnce()
    expect(activeText(wrapper)).toContain(ZODIACS[0].nameRu)
  })

  it('moves programmatically when the parent changes sign without repeated movements', async () => {
    const { wrapper, driver } = mountCarousel()
    await wrapper.setProps({ modelValue: 'ophiuchus' })
    expect(driver.slideToLoop).toHaveBeenCalledExactlyOnceWith(findIndexByKey('ophiuchus'))
    expect(activeText(wrapper)).toContain('Змееносец')
    await wrapper.setProps({ modelValue: 'ophiuchus' })
    expect(driver.slideToLoop).toHaveBeenCalledOnce()
  })

  it('accepts a keyboard-style click on a focused native arrow exactly once', async () => {
    const { wrapper, driver } = mountCarousel()
    const next = wrapper.get('button[aria-label="Next sign"]')
    ;(next.element as HTMLButtonElement).focus()
    expect(document.activeElement).toBe(next.element)
    // Browsers synthesize a click with detail=0 for keyboard activation. jsdom
    // cannot prove that Enter/Space actually generates it; browser smoke must.
    next.element.dispatchEvent(new MouseEvent('click', { detail: 0, bubbles: true }))
    await flushPromises()
    expect(driver.slideNext).toHaveBeenCalledOnce()
    expect(wrapper.emitted('update:modelValue')).toEqual([['taurus']])
  })

  it.each([-1, ZODIACS.length, 0.5, NaN, Infinity])('ignores invalid realIndex %s without losing the current sign', async index => {
    const { wrapper, errors, slide } = mountCarousel()
    slide(index)
    await flushPromises()
    expect(errors).not.toHaveBeenCalled()
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    expect(activeText(wrapper)).toContain('Овен')
    slide(findIndexByKey('taurus'))
    await flushPromises()
    expect(wrapper.emitted('update:modelValue')).toEqual([['taurus']])
    expect(activeText(wrapper)).toContain('Телец')
  })
})

// A minimal router adapter exercises the carousel's v-model contract. It does
// not import or replace tests for HoroscopeView/ArchiveMonth's own watchers.
async function mountRouteHarness() {
  const swiper = swiperDouble()
  const RouteHost = defineComponent({
    setup() {
      const route = useRoute()
      const router = useRouter()
      const sign = computed({
        get: () => String(route.params.sign),
        set: value => {
          if (value !== route.params.sign) {
            void router.replace({ name: 'carousel', params: { ...route.params, sign: value } })
          }
        },
      })
      return () => h(ZodiacCarousel, {
        modelValue: sign.value,
        'onUpdate:modelValue': value => { sign.value = value },
      })
    },
  })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/horoscope/:sign/:day', name: 'carousel', component: RouteHost }],
  })
  await router.push('/horoscope/aries/2026-11-15')
  await router.isReady()
  const wrapper = mount(RouterView, { global: { plugins: [router], stubs: swiper.stubs } })
  cleanups.push(() => wrapper.unmount())
  await flushPromises()
  return { wrapper, router, ...swiper }
}

describe('ZodiacCarousel with a minimal memory-router adapter (Swiper double)', () => {
  it('updates the route sign while preserving the explicit date', async () => {
    const { wrapper, router } = await mountRouteHarness()
    await wrapper.get('button[aria-label="Next sign"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/horoscope/taurus/2026-11-15')
    expect(activeText(wrapper)).toContain('Телец')
  })

  it('follows route changes, Back and Forward without resetting the sign', async () => {
    const { wrapper, router, driver } = await mountRouteHarness()
    await router.push('/horoscope/leo/2026-11-14')
    await flushPromises()
    expect(driver.realIndex).toBe(findIndexByKey('leo'))
    router.back()
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/horoscope/aries/2026-11-15')
    expect(activeText(wrapper)).toContain('Овен')
    router.forward()
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/horoscope/leo/2026-11-14')
    expect(activeText(wrapper)).toContain('Лев')
  })

  it('retains the final sign over repeated route navigation and a same-sign day change', async () => {
    const { wrapper, router, driver } = await mountRouteHarness()
    for (const { key, nameRu } of [...ZODIACS, ...ZODIACS].reverse()) {
      await router.push(`/horoscope/${key}/2026-11-15`)
      await flushPromises()
      expect(driver.realIndex).toBe(findIndexByKey(key))
      expect(activeText(wrapper)).toContain(nameRu)
    }
    driver.slideToLoop.mockClear()
    await router.push('/horoscope/capricorn/2026-11-14')
    await flushPromises()
    expect(driver.slideToLoop).not.toHaveBeenCalled()
    expect(activeText(wrapper)).toContain('Козерог')
  })
})
