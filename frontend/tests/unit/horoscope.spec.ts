import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'

import DaySlider from '../../src/components/DaySlider.vue'

describe('DaySlider', () => {
  it('formats today as Сегодня', () => {
    const today = new Date().toISOString().slice(0,10)
    const wrapper = mount(DaySlider, { props: { modelValue: today } })
    expect(wrapper.text()).toContain('Сегодня')
  })
})
