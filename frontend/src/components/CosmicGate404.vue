<script setup>
const SEGMENT_COUNT = 64
const PARTICLE_COUNT = 44
const STAR_COUNT = 90

function random(seed) {
  const x = Math.sin(seed * 12.9898 + 78.233) * 43758.5453
  return x - Math.floor(x)
}

function range(seed, min, max) {
  return min + (max - min) * random(seed)
}

function polarPoint(angleDeg, radius) {
  const angle = (angleDeg * Math.PI) / 180

  return {
    x: Math.cos(angle) * radius,
    y: Math.sin(angle) * radius,
  }
}

const segments = Array.from({ length: SEGMENT_COUNT }, (_, index) => {
  const angle = (360 / SEGMENT_COUNT) * index
  const startAngle = range(index + 100, 0, 360)
  const startRadius = range(index + 200, 185, 295)
  const start = polarPoint(startAngle, startRadius)

  return {
    id: `segment-${index}`,
    style: {
      '--angle': angle,
      '--start-x': `${start.x}px`,
      '--start-y': `${start.y}px`,
      '--start-rot': range(index + 300, -220, 220),
      '--assemble-delay': `${range(index + 400, 0, 0.42).toFixed(2)}s`,
      '--ignite-delay': `${(index * 0.018).toFixed(3)}s`,
    },
  }
})

const particles = Array.from({ length: PARTICLE_COUNT }, (_, index) => {
  const start = polarPoint(range(index + 500, 0, 360), range(index + 600, 170, 310))
  const end = polarPoint(range(index + 700, 0, 360), range(index + 800, 112, 162))

  return {
    id: `particle-${index}`,
    style: {
      '--particle-start-x': `${start.x}px`,
      '--particle-start-y': `${start.y}px`,
      '--particle-end-x': `${end.x}px`,
      '--particle-end-y': `${end.y}px`,
      '--particle-size': `${range(index + 900, 2, 4).toFixed(1)}px`,
      '--particle-delay': `${range(index + 1000, 0, 1.05).toFixed(2)}s`,
      '--particle-duration': `${range(index + 1100, 1.1, 1.9).toFixed(2)}s`,
    },
  }
})

const stars = Array.from({ length: STAR_COUNT }, (_, index) => ({
  id: `star-${index}`,
  style: {
    '--star-left': `${range(index + 1200, 0, 100).toFixed(2)}%`,
    '--star-top': `${range(index + 1300, 0, 100).toFixed(2)}%`,
    '--star-size': `${range(index + 1400, 1, 2.8).toFixed(1)}px`,
    '--star-delay': `${range(index + 1500, 0, 4).toFixed(2)}s`,
    '--star-opacity': range(index + 1600, 0.22, 0.95).toFixed(2),
  },
}))
</script>

<template>
  <section class="cosmic-gate404">
    <div class="cosmic-gate404__scene" aria-hidden="true">
      <span
        v-for="star in stars"
        :key="star.id"
        class="cosmic-gate404__star"
        :style="star.style"
      />

      <span
        v-for="particle in particles"
        :key="particle.id"
        class="cosmic-gate404__particle"
        :style="particle.style"
      />

      <div class="cosmic-gate404__planet" />

      <div class="cosmic-gate404__gate">
        <div class="cosmic-gate404__ring cosmic-gate404__ring--outer" />
        <div class="cosmic-gate404__ring cosmic-gate404__ring--middle" />
        <div class="cosmic-gate404__ring cosmic-gate404__ring--inner" />

        <div class="cosmic-gate404__event-horizon" />

        <span
          v-for="segment in segments"
          :key="segment.id"
          class="cosmic-gate404__segment"
          :style="segment.style"
        >
          <span class="cosmic-gate404__segment-shell" />
          <span class="cosmic-gate404__segment-light" />
        </span>

        <div class="cosmic-gate404__kawoosh" />
      </div>

      <div class="cosmic-gate404__scanline" />
    </div>

    <div v-if="$slots.default" class="cosmic-gate404__copy">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.cosmic-gate404 {
  --scene-size: 420px;
  --gate-size: 330px;
  --gate-radius-neg: -134px;
  --segment-width: 7px;
  --segment-height: 35px;

  width: min(100%, var(--scene-size));
  max-width: 100%;
  margin-inline: auto;
  color: #dff7ff;
  isolation: isolate;
}

.cosmic-gate404__scene {
  position: relative;
  width: 100%;
  aspect-ratio: 1;
  overflow: hidden;
  border: 1px solid rgba(116, 202, 255, 0.14);
  border-radius: 32px;
  background:
    radial-gradient(circle at 50% 48%, rgba(69, 187, 255, 0.16), transparent 38%),
    radial-gradient(circle at 15% 15%, rgba(130, 78, 255, 0.2), transparent 34%),
    radial-gradient(circle at 80% 80%, rgba(10, 142, 255, 0.12), transparent 38%),
    linear-gradient(180deg, #0b1021 0%, #050713 100%);
  box-shadow:
    inset 0 0 46px rgba(82, 199, 255, 0.08),
    0 20px 70px rgba(0, 0, 0, 0.22);
}

.cosmic-gate404__star {
  position: absolute;
  left: var(--star-left);
  top: var(--star-top);
  width: var(--star-size);
  height: var(--star-size);
  border-radius: 999px;
  background: rgba(225, 249, 255, var(--star-opacity));
  box-shadow: 0 0 10px rgba(112, 211, 255, 0.65);
  animation: cosmic-star-twinkle 3.8s ease-in-out var(--star-delay) infinite;
}

.cosmic-gate404__planet {
  position: absolute;
  right: -120px;
  bottom: -118px;
  width: 270px;
  aspect-ratio: 1;
  border-radius: 50%;
  background:
    radial-gradient(circle at 35% 28%, rgba(255, 255, 255, 0.26), transparent 10%),
    radial-gradient(circle at 48% 48%, rgba(78, 170, 255, 0.36), rgba(28, 42, 91, 0.16) 54%, transparent 72%);
  opacity: 0.48;
  filter: blur(0.2px);
}

.cosmic-gate404__particle {
  position: absolute;
  left: 50%;
  top: 50%;
  width: var(--particle-size);
  height: var(--particle-size);
  border-radius: 2px;
  background: rgba(125, 222, 255, 0.88);
  box-shadow: 0 0 10px rgba(86, 202, 255, 0.8);
  opacity: 0;
  transform: translate(var(--particle-start-x), var(--particle-start-y)) scale(0.3);
  animation: cosmic-particle-assemble var(--particle-duration) ease-out var(--particle-delay) both;
}

.cosmic-gate404__gate {
  position: absolute;
  left: 50%;
  top: 50%;
  z-index: 3;
  width: var(--gate-size);
  aspect-ratio: 1;
  transform: translate(-50%, -50%);
}

.cosmic-gate404__ring {
  position: absolute;
  border-radius: 50%;
  opacity: 0;
  animation:
    cosmic-ring-awake 0.9s ease-out 1.55s forwards,
    cosmic-ring-hum 4.8s ease-in-out 3.3s infinite;
}

.cosmic-gate404__ring--outer {
  inset: 0;
  border: 1px solid rgba(104, 209, 255, 0.35);
  box-shadow:
    0 0 28px rgba(55, 190, 255, 0.18),
    inset 0 0 24px rgba(55, 190, 255, 0.12);
}

.cosmic-gate404__ring--middle {
  inset: 28px;
  border: 1px dashed rgba(154, 229, 255, 0.22);
}

.cosmic-gate404__ring--inner {
  inset: 58px;
  border: 1px solid rgba(86, 178, 255, 0.2);
  box-shadow: inset 0 0 28px rgba(43, 179, 255, 0.08);
}

.cosmic-gate404__segment {
  position: absolute;
  left: 50%;
  top: 50%;
  z-index: 5;
  width: var(--segment-width);
  height: var(--segment-height);
  opacity: 0;
  transform-origin: center;
  transform:
    translate(var(--start-x), var(--start-y))
    rotate(calc(var(--start-rot) * 1deg))
    scale(0.28);
  animation: cosmic-segment-assemble 1.38s cubic-bezier(0.2, 0.9, 0.22, 1.18) var(--assemble-delay) both;
}

.cosmic-gate404__segment-shell,
.cosmic-gate404__segment-light {
  position: absolute;
  border-radius: 999px;
}

.cosmic-gate404__segment-shell {
  inset: 0;
  background:
    linear-gradient(180deg, rgba(196, 234, 255, 0.38), rgba(20, 39, 78, 0.85)),
    linear-gradient(90deg, rgba(6, 10, 24, 0.9), rgba(35, 79, 125, 0.95), rgba(6, 10, 24, 0.9));
  border: 1px solid rgba(140, 220, 255, 0.24);
  box-shadow:
    0 0 0 1px rgba(11, 20, 38, 0.85),
    0 0 14px rgba(56, 190, 255, 0.12);
}

.cosmic-gate404__segment-light {
  left: 50%;
  top: 18%;
  width: 44%;
  height: 64%;
  transform: translateX(-50%);
  background: linear-gradient(180deg, #effcff, #62d4ff 48%, #237dff);
  opacity: 0.08;
  box-shadow: 0 0 0 rgba(87, 210, 255, 0);
  animation:
    cosmic-segment-ignite 1.25s ease-out calc(1.7s + var(--ignite-delay)) both,
    cosmic-segment-flicker 2.8s ease-in-out calc(3.35s + var(--ignite-delay)) infinite;
}

.cosmic-gate404__event-horizon {
  position: absolute;
  left: 50%;
  top: 50%;
  z-index: 2;
  width: 68%;
  aspect-ratio: 1;
  overflow: hidden;
  border-radius: 50%;
  opacity: 0;
  transform: translate(-50%, -50%) scale(0.04);
  background:
    radial-gradient(circle at 46% 45%, rgba(255, 255, 255, 0.98) 0 7%, rgba(210, 248, 255, 0.92) 8% 14%, rgba(93, 205, 255, 0.78) 26%, rgba(39, 86, 194, 0.62) 48%, rgba(5, 9, 36, 0.12) 70%),
    conic-gradient(from 30deg, rgba(100, 225, 255, 0.5), rgba(73, 75, 236, 0.36), rgba(204, 246, 255, 0.62), rgba(100, 225, 255, 0.5));
  box-shadow:
    0 0 42px rgba(93, 210, 255, 0.56),
    0 0 90px rgba(53, 112, 255, 0.3),
    inset 0 0 36px rgba(255, 255, 255, 0.42);
  animation:
    cosmic-horizon-open 1.65s cubic-bezier(0.16, 1, 0.3, 1) 2.45s forwards,
    cosmic-horizon-pulse 4.4s ease-in-out 4.1s infinite;
}

.cosmic-gate404__event-horizon::before,
.cosmic-gate404__event-horizon::after {
  content: '';
  position: absolute;
  inset: -15%;
  border-radius: 50%;
}

.cosmic-gate404__event-horizon::before {
  background: conic-gradient(
    from 0deg,
    transparent,
    rgba(255, 255, 255, 0.52),
    transparent,
    rgba(70, 195, 255, 0.44),
    transparent
  );
  opacity: 0.48;
  mix-blend-mode: screen;
  animation: cosmic-horizon-spin 5.6s linear 2.8s infinite;
}

.cosmic-gate404__event-horizon::after {
  inset: 0;
  background:
    linear-gradient(rgba(255, 255, 255, 0.08) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.06) 1px, transparent 1px);
  background-size: 8px 8px;
  opacity: 0.22;
  mix-blend-mode: screen;
  animation: cosmic-pixel-drift 2.2s steps(5) 3.8s infinite;
}

.cosmic-gate404__kawoosh {
  position: absolute;
  left: 50%;
  top: 50%;
  z-index: 7;
  width: 40%;
  aspect-ratio: 1;
  border-radius: 50%;
  opacity: 0;
  transform: translate(-50%, -50%) scale(0.08);
  background:
    radial-gradient(circle, rgba(255, 255, 255, 0.96) 0 16%, rgba(113, 226, 255, 0.72) 17% 34%, rgba(65, 124, 255, 0.26) 44%, transparent 68%);
  mix-blend-mode: screen;
  animation: cosmic-kawoosh 0.95s ease-out 2.55s both;
}

.cosmic-gate404__ship {
  position: absolute;
  z-index: 4;
  width: 30px;
  height: 8px;
  opacity: 0;
  border-radius: 999px 60% 60% 999px;
  background:
    linear-gradient(90deg, rgba(207, 237, 255, 0.9), rgba(71, 97, 137, 0.9) 58%, rgba(8, 16, 34, 0.94));
  box-shadow:
    -8px 0 14px rgba(62, 190, 255, 0.36),
    0 0 10px rgba(150, 220, 255, 0.18);
  animation: cosmic-ship-enter 1.2s ease-out 3.1s forwards;
}

.cosmic-gate404__ship--one {
  left: 13%;
  top: 40%;
  transform: rotate(-7deg) scale(0.82);
}

.cosmic-gate404__ship--two {
  left: 19%;
  top: 57%;
  transform: rotate(8deg) scale(0.62);
  animation-delay: 3.3s;
}

.cosmic-gate404__ship--three {
  left: 28%;
  top: 47%;
  transform: rotate(2deg) scale(0.48);
  animation-delay: 3.48s;
}

.cosmic-gate404__scanline {
  position: absolute;
  inset: 0;
  z-index: 9;
  pointer-events: none;
  background: linear-gradient(
    180deg,
    transparent,
    rgba(255, 255, 255, 0.035),
    transparent
  );
  background-size: 100% 8px;
  opacity: 0.28;
  mix-blend-mode: screen;
  animation: cosmic-scanline 7s linear infinite;
}

.cosmic-gate404__copy {
  margin-top: 22px;
  text-align: center;
}

.cosmic-gate404__copy :deep(h1) {
  margin: 0;
  font-size: clamp(2.4rem, 8vw, 5rem);
  line-height: 1;
  letter-spacing: 0.06em;
}

.cosmic-gate404__copy :deep(p) {
  max-width: 36rem;
  margin: 12px auto 0;
  color: rgba(223, 247, 255, 0.78);
}

@keyframes cosmic-segment-assemble {
  0% {
    opacity: 0;
    transform:
      translate(var(--start-x), var(--start-y))
      rotate(calc(var(--start-rot) * 1deg))
      scale(0.28);
  }

  64% {
    opacity: 1;
  }

  78% {
    transform:
      translate(-50%, -50%)
      rotate(calc(var(--angle) * 1deg))
      translateY(calc(var(--gate-radius-neg) - 8px))
      scale(1.08);
  }

  100% {
    opacity: 1;
    transform:
      translate(-50%, -50%)
      rotate(calc(var(--angle) * 1deg))
      translateY(var(--gate-radius-neg))
      scale(1);
  }
}

@keyframes cosmic-segment-ignite {
  0% {
    opacity: 0.08;
    box-shadow: 0 0 0 rgba(87, 210, 255, 0);
  }

  38% {
    opacity: 1;
    box-shadow:
      0 0 9px rgba(145, 234, 255, 0.95),
      0 0 24px rgba(57, 190, 255, 0.65);
  }

  100% {
    opacity: 0.72;
    box-shadow:
      0 0 7px rgba(145, 234, 255, 0.72),
      0 0 18px rgba(57, 190, 255, 0.38);
  }
}

@keyframes cosmic-segment-flicker {
  0%,
  100% {
    opacity: 0.62;
  }

  50% {
    opacity: 0.92;
  }
}

@keyframes cosmic-ring-awake {
  from {
    opacity: 0;
    transform: scale(0.96);
  }

  to {
    opacity: 1;
    transform: scale(1);
  }
}

@keyframes cosmic-ring-hum {
  0%,
  100% {
    filter: drop-shadow(0 0 8px rgba(69, 190, 255, 0.16));
  }

  50% {
    filter: drop-shadow(0 0 18px rgba(69, 190, 255, 0.34));
  }
}

@keyframes cosmic-horizon-open {
  0% {
    opacity: 0;
    filter: blur(10px);
    transform: translate(-50%, -50%) scale(0.04);
  }

  42% {
    opacity: 1;
    filter: blur(2px);
    transform: translate(-50%, -50%) scale(1.18);
  }

  72% {
    transform: translate(-50%, -50%) scale(0.96);
  }

  100% {
    opacity: 1;
    filter: blur(0);
    transform: translate(-50%, -50%) scale(1);
  }
}

@keyframes cosmic-horizon-pulse {
  0%,
  100% {
    transform: translate(-50%, -50%) scale(1);
    filter: brightness(1);
  }

  50% {
    transform: translate(-50%, -50%) scale(1.035);
    filter: brightness(1.15);
  }
}

@keyframes cosmic-horizon-spin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes cosmic-kawoosh {
  0% {
    opacity: 0;
    transform: translate(-50%, -50%) scale(0.08);
  }

  16% {
    opacity: 1;
  }

  48% {
    opacity: 0.85;
    transform: translate(-50%, -50%) scale(1.45);
  }

  100% {
    opacity: 0;
    transform: translate(-50%, -50%) scale(2.2);
  }
}

@keyframes cosmic-particle-assemble {
  0% {
    opacity: 0;
    transform: translate(var(--particle-start-x), var(--particle-start-y)) scale(0.22);
  }

  18% {
    opacity: 1;
  }

  72% {
    opacity: 0.9;
    transform: translate(var(--particle-end-x), var(--particle-end-y)) scale(1);
  }

  100% {
    opacity: 0;
    transform: translate(var(--particle-end-x), var(--particle-end-y)) scale(0.3);
  }
}

@keyframes cosmic-star-twinkle {
  0%,
  100% {
    transform: scale(0.75);
    opacity: calc(var(--star-opacity) * 0.6);
  }

  50% {
    transform: scale(1.15);
    opacity: var(--star-opacity);
  }
}

@keyframes cosmic-pixel-drift {
  from {
    transform: translate(0, 0);
  }

  to {
    transform: translate(8px, 8px);
  }
}

@keyframes cosmic-ship-enter {
  from {
    opacity: 0;
    margin-left: -18px;
  }

  to {
    opacity: 0.82;
    margin-left: 0;
  }
}

@keyframes cosmic-scanline {
  from {
    background-position-y: 0;
  }

  to {
    background-position-y: 80px;
  }
}

@media (max-width: 540px) {
  .cosmic-gate404 {
    --scene-size: 320px;
    --gate-size: 274px;
    --gate-radius-neg: -111px;
    --segment-width: 6px;
    --segment-height: 28px;
  }

  .cosmic-gate404__scene {
    border-radius: 26px;
  }

  .cosmic-gate404__ship {
    display: none;
  }

  .cosmic-gate404__planet {
    right: -118px;
    bottom: -120px;
    width: 240px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .cosmic-gate404__star,
  .cosmic-gate404__particle,
  .cosmic-gate404__ring,
  .cosmic-gate404__segment,
  .cosmic-gate404__segment-light,
  .cosmic-gate404__event-horizon,
  .cosmic-gate404__event-horizon::before,
  .cosmic-gate404__event-horizon::after,
  .cosmic-gate404__kawoosh,
  .cosmic-gate404__ship,
  .cosmic-gate404__scanline {
    animation: none !important;
  }

  .cosmic-gate404__particle,
  .cosmic-gate404__kawoosh,
  .cosmic-gate404__scanline {
    display: none;
  }

  .cosmic-gate404__ring,
  .cosmic-gate404__segment,
  .cosmic-gate404__event-horizon,
  .cosmic-gate404__ship {
    opacity: 1;
  }

  .cosmic-gate404__segment {
    transform:
      translate(-50%, -50%)
      rotate(calc(var(--angle) * 1deg))
      translateY(var(--gate-radius-neg))
      scale(1);
  }

  .cosmic-gate404__segment-light {
    opacity: 0.72;
  }

  .cosmic-gate404__event-horizon {
    transform: translate(-50%, -50%) scale(1);
  }
}
</style>