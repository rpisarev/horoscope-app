<template>
  <canvas
    ref="canvas"
    aria-hidden="true"
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

let ctx = null
let motionPreference = null
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
  const surface = canvas.value
  if (!surface) return

  if (stars.length && surface.width && surface.height) {
    const scaleX = window.innerWidth / surface.width
    const scaleY = window.innerHeight / surface.height
    for (const star of stars) {
      star.x *= scaleX
      star.y *= scaleY
    }
  } else {
    seedStars()
  }
  surface.width = window.innerWidth
  surface.height = window.innerHeight
  drawStars(0)
}

function spawnStar() {
  if (!isRunning) return

  stars.push(createStar({ fromLeft: true }))
}

function drawStars(dt) {
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
}

function tick(now) {
  if (!isRunning) return
  drawStars((now - prev) / 1000)
  prev = now
  animationFrameId = window.requestAnimationFrame(tick)
}

function stopMotion() {
  isRunning = false

  if (spawnIntervalId !== null) {
    window.clearInterval(spawnIntervalId)
    spawnIntervalId = null
  }

  if (animationFrameId !== null) {
    window.cancelAnimationFrame(animationFrameId)
    animationFrameId = null
  }
}

function syncMotion() {
  if (motionPreference?.matches) {
    stopMotion()
    return
  }
  if (isRunning) return

  isRunning = true
  prev = performance.now()
  spawnIntervalId = window.setInterval(spawnStar, spawnDelay)
  animationFrameId = window.requestAnimationFrame(tick)
}

onMounted(() => {
  ctx = canvas.value?.getContext('2d')
  if (!ctx) return

  resize()
  window.addEventListener('resize', resize)
  motionPreference = window.matchMedia?.('(prefers-reduced-motion: reduce)')
  motionPreference?.addEventListener('change', syncMotion)
  syncMotion()
})

onUnmounted(() => {
  motionPreference?.removeEventListener('change', syncMotion)
  window.removeEventListener('resize', resize)
  stopMotion()
  stars.length = 0
  ctx = null
})
</script>
