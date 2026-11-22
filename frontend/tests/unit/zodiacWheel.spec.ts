import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import ZodiacWheel from '../../src/components/ZodiacWheel.vue'
import { HOME_ZODIACS } from '../../src/constants/zodiac'

const cleanups: Array<() => void> = []
afterEach(() => cleanups.splice(0).forEach(cleanup => cleanup()))

function mountWheel() {
  const wrapper = mount(ZodiacWheel, {
    props: { zodiacs: HOME_ZODIACS },
    attachTo: document.body,
  })
  cleanups.push(() => wrapper.unmount())
  return wrapper
}

describe('ZodiacWheel selection and animation contract', () => {
  it.each(['click', 'keydown.enter', 'keydown.space'])('%s emits each original sign exactly once', async event => {
    const wrapper = mountWheel()
    const signs = wrapper.findAll('[role="button"]')
    expect(signs).toHaveLength(HOME_ZODIACS.length)
    for (const [index, sign] of signs.entries()) {
      expect(sign.attributes('tabindex')).toBe('0')
      expect(sign.get('small').text()).toBe(HOME_ZODIACS[index].name)
      await sign.trigger(event)
    }
    expect(wrapper.emitted('select')).toEqual(HOME_ZODIACS.map(sign => [sign]))
  })

  it('prevents Enter/Space defaults without selecting on unrelated keys', () => {
    const wrapper = mountWheel()
    const sign = wrapper.get('[role="button"]')
    for (const key of ['Enter', ' ']) {
      const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true })
      sign.element.dispatchEvent(event)
      expect(event.defaultPrevented).toBe(true)
    }
    sign.element.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }))
    expect(wrapper.emitted('select')).toHaveLength(2)
  })

  it('pauses both rotation directions on hover, supplies matching details, and resumes on leave', async () => {
    const wrapper = mountWheel()
    const signs = wrapper.findAll('[role="button"]')
    const rotations = () => wrapper.findAll('.animate-spin-slow, .animate-spin-inner-reverse')
    for (const index of [0, HOME_ZODIACS.length - 1]) {
      await signs[index].trigger('mouseenter')
      expect(rotations().every(el => (el.element as HTMLElement).style.animationPlayState === 'paused')).toBe(true)
      for (const tooltip of [signs[index].get('.wheel-tooltip-orbit'), wrapper.get('.wheel-tooltip-center')]) {
        expect(tooltip.text()).toContain(HOME_ZODIACS[index].name)
        expect(tooltip.text()).toContain(HOME_ZODIACS[index].range)
      }
      await signs[index].trigger('mouseleave')
      expect(rotations().every(el => (el.element as HTMLElement).style.animationPlayState === 'running')).toBe(true)
      expect(wrapper.find('h3').exists()).toBe(false)
    }
    expect(wrapper.emitted('select')).toBeUndefined()
  })

  it('keeps focused sign identity when props refresh and removes the wheel on unmount', async () => {
    const wrapper = mountWheel()
    const sign = wrapper.findAll('[role="button"]')[8].element as HTMLElement
    sign.focus()
    await wrapper.setProps({ zodiacs: [...HOME_ZODIACS] })
    expect(document.activeElement).toBe(sign)
    wrapper.unmount()
    cleanups.pop()
    expect(document.body.querySelector('.zodiac-wheel')).toBeNull()
  })

  it('shows the latest hovered or focused sign and resumes only after both leave', async () => {
    const wrapper = mountWheel()
    const [aries, taurus] = wrapper.findAll('[role="button"]')
    const detail = () => wrapper.get('.wheel-tooltip-center').text()
    const playStates = () => wrapper.findAll('.wheel-orbit, .wheel-sign')
      .map(el => (el.element as HTMLElement).style.animationPlayState)

    await taurus.trigger('mouseenter')
    await aries.trigger('focus')
    expect(aries.attributes('aria-label')).toBe(HOME_ZODIACS[0].name)
    expect(aries.attributes('aria-description')).toBe(HOME_ZODIACS[0].range)
    expect(detail()).toContain(HOME_ZODIACS[0].range)
    await aries.trigger('blur')
    expect(detail()).toContain(HOME_ZODIACS[1].range)
    await taurus.trigger('mouseleave')
    await aries.trigger('focus')
    await taurus.trigger('mouseenter')
    expect(detail()).toContain(HOME_ZODIACS[1].range)
    await taurus.trigger('mouseleave')
    expect(detail()).toContain(HOME_ZODIACS[0].range)
    expect(new Set(playStates())).toEqual(new Set(['paused']))
    await aries.trigger('blur')
    expect(wrapper.find('h3').exists()).toBe(false)
    expect(new Set(playStates())).toEqual(new Set(['running']))
    expect(wrapper.emitted('select')).toBeUndefined()
  })

  it('renders an empty input without targets or details', () => {
    const wrapper = mount(ZodiacWheel)
    expect(wrapper.find('[role="button"]').exists()).toBe(false)
    expect(wrapper.find('h3').exists()).toBe(false)
    wrapper.unmount()
  })
})
