import { mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import Starfield from '../../src/components/Starfield.vue'

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

it.each([true, false])('honors reduced motion on mount (%s), on change and on unmount', reduced => {
  const preference = Object.assign(new EventTarget(), { matches: reduced })
  const matchMedia = vi.fn(() => preference)
  vi.stubGlobal('matchMedia', matchMedia)

  const graphics = { fillRect: vi.fn(), beginPath: vi.fn(), arc: vi.fn(), fill: vi.fn() }
  vi.stubGlobal('innerWidth', 320)
  vi.stubGlobal('innerHeight', 568)
  vi.spyOn(Math, 'random').mockReturnValue(0.5)
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext')
    .mockReturnValue(graphics as unknown as CanvasRenderingContext2D)
  const requestFrame = vi.fn((_callback: FrameRequestCallback) => 131)
  const cancelFrame = vi.fn()
  vi.stubGlobal('requestAnimationFrame', requestFrame)
  vi.stubGlobal('cancelAnimationFrame', cancelFrame)
  const setInterval = vi.spyOn(window, 'setInterval').mockReturnValue(137)
  const clearInterval = vi.spyOn(window, 'clearInterval')
  const removeChange = vi.spyOn(preference, 'removeEventListener')
  const removeResize = vi.spyOn(window, 'removeEventListener')

  function change(matches: boolean) {
    preference.matches = matches
    preference.dispatchEvent(new Event('change'))
  }

  const wrapper = mount(Starfield)
  try {
    expect(matchMedia).toHaveBeenCalledWith('(prefers-reduced-motion: reduce)')
    expect(graphics.arc).toHaveBeenCalled()
    expect(requestFrame).toHaveBeenCalledTimes(reduced ? 0 : 1)
    expect(setInterval).toHaveBeenCalledTimes(reduced ? 0 : 1)

    change(false)
    change(false)
    expect(setInterval).toHaveBeenCalledExactlyOnceWith(expect.any(Function), 250)
    expect(requestFrame).toHaveBeenCalledTimes(1)
    const tick = requestFrame.mock.calls[0][0]
    tick(performance.now() + 16)
    expect(requestFrame).toHaveBeenCalledTimes(2)

    change(true)
    expect(cancelFrame).toHaveBeenCalledWith(131)
    expect(clearInterval).toHaveBeenCalledWith(137)
    tick(performance.now() + 32)
    expect(requestFrame).toHaveBeenCalledTimes(2)
    const framesDrawn = graphics.fillRect.mock.calls.length
    const [x, y, radius] = graphics.arc.mock.lastCall!
    vi.stubGlobal('innerWidth', 1280)
    vi.stubGlobal('innerHeight', 852)
    window.dispatchEvent(new Event('resize'))
    expect(graphics.fillRect).toHaveBeenCalledTimes(framesDrawn + 1)
    expect(graphics.arc.mock.lastCall!.slice(0, 3)).toEqual([x * 4, y * 1.5, radius])
    expect(requestFrame).toHaveBeenCalledTimes(2)

    change(false)
    expect(setInterval).toHaveBeenCalledTimes(2)
    expect(requestFrame).toHaveBeenCalledTimes(3)
  } finally {
    wrapper.unmount()
  }

  expect(removeChange).toHaveBeenCalledWith('change', expect.any(Function))
  expect(removeResize).toHaveBeenCalledWith('resize', expect.any(Function))
  expect(cancelFrame).toHaveBeenCalledTimes(2)
  expect(clearInterval).toHaveBeenCalledTimes(2)
  change(false)
  expect(requestFrame).toHaveBeenCalledTimes(3)
})
