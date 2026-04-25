<template>
  <canvas
    ref="canvas"
    class="fixed inset-0 z-0 pointer-events-none"
  ></canvas>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

const canvas = ref(null)
const stars = []

// Individual star speed range for a subtle parallax-like effect
const minSpeed = 100
const maxSpeed = 140
const spawnDelay = 250

// Starfield is mounted only on the Home page, so route navigation unmounts it.
// The animation uses both requestAnimationFrame and setInterval, which can keep
// running after navigation if they are not explicitly stopped. If a stale frame
// or interval tries to draw on a destroyed canvas, it can break the app state
// during client-side navigation: the route changes, but the next page may look
// as if its scripts did not initialize until a full page reload.
//
// To avoid that, this component keeps all animation handles in module-local
// variables and guards every async callback with isRunning. onUnmounted() must
// always stop the loop, clear the interval, remove the resize listener, and
// release the canvas context.
let ctx = null
let animationFrameId = null
let spawnIntervalId = null
let prev = 0
let isRunning = false

function randomStarSpeed() {
  return minSpeed + Math.random() * (maxSpeed - minSpeed)
}

function createStar({ fromLeft = true } = {}) {
  return {
    x: fromLeft ? -2 : Math.random() * window.innerWidth,
    y: Math.random() * window.innerHeight,
    r: Math.random() * 2 + 1,
    speed: randomStarSpeed(),
  }
}

function initialStarCount() {
  return Math.max(45, Math.round((window.innerWidth * window.innerHeight) / 18000))
}

function seedStars() {
  stars.length = 0

  for (let i = 0; i < initialStarCount(); i++) {
    stars.push(createStar({ fromLeft: false }))
  }
}

function resize() {
  if (!canvas.value) return

  canvas.value.width = window.innerWidth
  canvas.value.height = window.innerHeight
}

function spawnStar() {
  if (!isRunning) return

  stars.push(createStar({ fromLeft: true }))
}

function tick(now) {
  if (!isRunning || !ctx) return

  const dt = (now - prev) / 1000
  prev = now

  ctx.fillStyle = '#070b19'
  ctx.fillRect(0, 0, window.innerWidth, window.innerHeight)

  for (let i = stars.length - 1; i >= 0; i--) {
    const s = stars[i]

    s.x += s.speed * dt

    if (s.x > window.innerWidth + 4) {
      stars.splice(i, 1)
    } else {
      ctx.fillStyle = '#fff'
      ctx.beginPath()
      ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2)
      ctx.fill()
    }
  }

  animationFrameId = window.requestAnimationFrame(tick)
}

onMounted(() => {
  if (!canvas.value) return

  ctx = canvas.value.getContext('2d')
  if (!ctx) return

  isRunning = true
  prev = performance.now()

  resize()
  seedStars()

  window.addEventListener('resize', resize)

  spawnIntervalId = window.setInterval(spawnStar, spawnDelay)
  animationFrameId = window.requestAnimationFrame(tick)
})

onUnmounted(() => {
  isRunning = false

  window.removeEventListener('resize', resize)

  if (spawnIntervalId !== null) {
    window.clearInterval(spawnIntervalId)
    spawnIntervalId = null
  }

  if (animationFrameId !== null) {
    window.cancelAnimationFrame(animationFrameId)
    animationFrameId = null
  }

  stars.length = 0
  ctx = null
})
</script>