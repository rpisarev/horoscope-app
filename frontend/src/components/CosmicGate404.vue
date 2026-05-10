<script setup>
const SEGMENT_COUNT = 56
const PARTICLE_COUNT = 46
const STAR_COUNT = 120

function random(seed) {
  const x = Math.sin(seed * 12.9898 + 78.233) * 43758.5453
  return x - Math.floor(x)
}

function range(seed, min, max) {
  return min + (max - min) * random(seed)
}

function pointOnEllipse(angleDeg, radiusX, radiusY) {
  const angle = (angleDeg * Math.PI) / 180

  return {
    x: Math.cos(angle) * radiusX,
    y: Math.sin(angle) * radiusY,
  }
}

const segments = Array.from({ length: SEGMENT_COUNT }, (_, index) => {
  const angle = (360 / SEGMENT_COUNT) * index
  const startAngle = range(index + 100, 0, 360)
  const start = pointOnEllipse(
    startAngle,
    range(index + 200, 250, 430),
    range(index + 300, 190, 360)
  )

  return {
    id: `segment-${index}`,
    style: {
      '--angle': `${angle.toFixed(3)}deg`,
      '--start-x': `${start.x.toFixed(1)}px`,
      '--start-y': `${start.y.toFixed(1)}px`,
      '--start-rot': `${range(index + 400, -220, 220).toFixed(1)}deg`,
      '--assemble-delay': `${range(index + 500, 0, 0.72).toFixed(2)}s`,
      '--ignite-delay': `${(index * 0.018).toFixed(3)}s`,
    },
  }
})

const particles = Array.from({ length: PARTICLE_COUNT }, (_, index) => {
  const start = pointOnEllipse(
    range(index + 600, 0, 360),
    range(index + 700, 360, 650),
    range(index + 800, 220, 390)
  )

  const end = pointOnEllipse(
    range(index + 900, 0, 360),
    range(index + 1000, 160, 250),
    range(index + 1100, 70, 135)
  )

  return {
    id: `particle-${index}`,
    style: {
      '--particle-start-x': `${start.x.toFixed(1)}px`,
      '--particle-start-y': `${start.y.toFixed(1)}px`,
      '--particle-end-x': `${end.x.toFixed(1)}px`,
      '--particle-end-y': `${end.y.toFixed(1)}px`,
      '--particle-size': `${range(index + 1200, 2, 5).toFixed(1)}px`,
      '--particle-delay': `${range(index + 1300, 0, 1.18).toFixed(2)}s`,
      '--particle-duration': `${range(index + 1400, 1.1, 2.1).toFixed(2)}s`,
    },
  }
})

const stars = Array.from({ length: STAR_COUNT }, (_, index) => ({
  id: `star-${index}`,
  style: {
    '--star-left': `${range(index + 1500, 0, 100).toFixed(2)}%`,
    '--star-top': `${range(index + 1600, 0, 100).toFixed(2)}%`,
    '--star-size': `${range(index + 1700, 1, 2.8).toFixed(1)}px`,
    '--star-delay': `${range(index + 1800, 0, 4.8).toFixed(2)}s`,
    '--star-opacity': range(index + 1900, 0.18, 0.95).toFixed(2),
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

      <div class="cosmic-gate404__nebula cosmic-gate404__nebula--one" />
      <div class="cosmic-gate404__nebula cosmic-gate404__nebula--two" />
      <div class="cosmic-gate404__planet" />

      <span
        v-for="particle in particles"
        :key="particle.id"
        class="cosmic-gate404__particle"
        :style="particle.style"
      />

      <div class="cosmic-gate404__gate-shell">
        <div class="cosmic-gate404__gate-shadow" />

        <div class="cosmic-gate404__gate-plane">
          <div class="cosmic-gate404__depth-echo" />
          <div class="cosmic-gate404__ring cosmic-gate404__ring--rear" />

          <div class="cosmic-gate404__event-horizon">
            <span class="cosmic-gate404__horizon-swirl" />
            <span class="cosmic-gate404__horizon-grid" />
          </div>

          <div class="cosmic-gate404__kawoosh" />

          <span
            v-for="segment in segments"
            :key="segment.id"
            class="cosmic-gate404__segment"
            :style="segment.style"
          >
            <span class="cosmic-gate404__segment-shell" />
            <span class="cosmic-gate404__segment-light" />
          </span>

          <div class="cosmic-gate404__ring cosmic-gate404__ring--front" />
          <div class="cosmic-gate404__ring cosmic-gate404__ring--inner" />
          <div class="cosmic-gate404__ignition-sweep" />
        </div>
      </div>

      <div class="cosmic-gate404__foreground-glow" />
      <div class="cosmic-gate404__scanline" />
    </div>

    <div v-if="$slots.default" class="cosmic-gate404__copy">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.cosmic-gate404 {
  --gate-size: clamp(360px, 48vw, 610px);
  --gate-radius: clamp(-258px, -20vw, -150px);
  --segment-width: clamp(7px, 0.82vw, 10px);
  --segment-height: clamp(34px, 3.4vw, 50px);

  width: min(100%, 1180px);
  margin-inline: auto;
  color: #dff7ff;
  isolation: isolate;
}

.cosmic-gate404__scene {
  position: relative;
  width: 100%;
  height: clamp(380px, 52vh, 560px);
  overflow: hidden;
  border: 1px solid rgba(116, 202, 255, 0.14);
  border-radius: 36px;
  background:
    radial-gradient(circle at 68% 42%, rgba(99, 210, 255, 0.18), transparent 34%),
    radial-gradient(circle at 20% 22%, rgba(139, 92, 246, 0.2), transparent 38%),
    radial-gradient(circle at 44% 110%, rgba(12, 120, 255, 0.16), transparent 46%),
    linear-gradient(180deg, #0b1021 0%, #050713 100%);
  box-shadow:
    inset 0 0 70px rgba(82, 199, 255, 0.08),
    0 22px 80px rgba(0, 0, 0, 0.25);
}

.cosmic-gate404__star {
  position: absolute;
  left: var(--star-left);
  top: var(--star-top);
  z-index: 1;
  width: var(--star-size);
  height: var(--star-size);
  border-radius: 999px;
  background: rgba(225, 249, 255, var(--star-opacity));
  box-shadow: 0 0 10px rgba(112, 211, 255, 0.62);
  animation: cosmic-star-twinkle 4.2s ease-in-out var(--star-delay) infinite;
}

.cosmic-gate404__nebula {
  position: absolute;
  z-index: 1;
  pointer-events: none;
  border-radius: 999px;
  filter: blur(28px);
  opacity: 0.55;
}

.cosmic-gate404__nebula--one {
  left: 41%;
  top: 8%;
  width: 360px;
  height: 160px;
  background: rgba(68, 92, 255, 0.28);
  transform: rotate(-14deg);
}

.cosmic-gate404__nebula--two {
  right: 8%;
  bottom: 8%;
  width: 390px;
  height: 210px;
  background: rgba(42, 194, 255, 0.18);
  transform: rotate(18deg);
}

.cosmic-gate404__planet {
  position: absolute;
  left: -120px;
  bottom: -210px;
  z-index: 1;
  width: clamp(360px, 40vw, 560px);
  aspect-ratio: 1;
  border-radius: 50%;
  background:
    radial-gradient(circle at 32% 28%, rgba(255, 255, 255, 0.28), transparent 9%),
    radial-gradient(circle at 40% 40%, rgba(96, 182, 255, 0.38), rgba(44, 61, 122, 0.28) 50%, rgba(5, 8, 22, 0) 72%);
  box-shadow:
    inset -36px -32px 70px rgba(0, 0, 0, 0.32),
    0 0 42px rgba(96, 182, 255, 0.16);
  opacity: 0.58;
}

.cosmic-gate404__particle {
  position: absolute;
  left: 62%;
  top: 46%;
  z-index: 4;
  width: var(--particle-size);
  height: var(--particle-size);
  border-radius: 2px;
  background: rgba(137, 226, 255, 0.92);
  box-shadow: 0 0 12px rgba(86, 202, 255, 0.86);
  opacity: 0;
  transform: translate(var(--particle-start-x), var(--particle-start-y)) scale(0.25);
  animation: cosmic-particle-assemble var(--particle-duration) ease-out var(--particle-delay) both;
}

.cosmic-gate404__gate-shell {
  position: absolute;
  left: 62%;
  top: 46%;
  z-index: 5;
  width: var(--gate-size);
  aspect-ratio: 1;
  perspective: 1200px;
  transform: translate(-50%, -50%);
}

.cosmic-gate404__gate-shadow {
  position: absolute;
  left: 50%;
  top: 54%;
  z-index: 0;
  width: 82%;
  height: 26%;
  border-radius: 50%;
  background: rgba(27, 180, 255, 0.2);
  filter: blur(36px);
  transform: translate(-50%, -50%) rotate(-12deg);
  opacity: 0;
  animation: cosmic-shadow-awake 1.2s ease-out 2.35s forwards;
}

.cosmic-gate404__gate-plane {
  position: absolute;
  inset: 0;
  z-index: 2;
  transform-style: preserve-3d;
  transform-origin: center center;
  transform: rotateX(5deg) rotateY(-52deg) rotateZ(-8deg);
  animation: cosmic-gate-idle 7s ease-in-out 4s infinite;
}

.cosmic-gate404__depth-echo,
.cosmic-gate404__ring {
  position: absolute;
  border-radius: 50%;
  pointer-events: none;
}

.cosmic-gate404__depth-echo {
  inset: 4%;
  z-index: 1;
  border: 20px solid rgba(15, 26, 58, 0.78);
  box-shadow:
    36px 12px 0 rgba(4, 9, 25, 0.56),
    42px 18px 28px rgba(0, 0, 0, 0.3);
  opacity: 0;
  transform: translate(28px, 10px) scale(0.97);
  animation: cosmic-ring-awake 0.9s ease-out 1.55s forwards;
}

.cosmic-gate404__ring--rear {
  inset: 5%;
  z-index: 2;
  border: 2px solid rgba(52, 167, 255, 0.22);
  box-shadow:
    34px 10px 0 rgba(13, 23, 52, 0.62),
    0 0 24px rgba(54, 190, 255, 0.12);
  opacity: 0;
  transform: translate(28px, 8px);
  animation: cosmic-ring-awake 0.9s ease-out 1.62s forwards;
}

.cosmic-gate404__ring--front {
  inset: 3%;
  z-index: 8;
  border: 2px solid rgba(151, 228, 255, 0.4);
  box-shadow:
    0 0 28px rgba(74, 202, 255, 0.23),
    inset 0 0 34px rgba(62, 190, 255, 0.12);
  opacity: 0;
  animation:
    cosmic-ring-awake 0.9s ease-out 1.7s forwards,
    cosmic-ring-hum 4.6s ease-in-out 3.6s infinite;
}

.cosmic-gate404__ring--inner {
  inset: 17%;
  z-index: 9;
  border: 1px solid rgba(187, 240, 255, 0.22);
  box-shadow:
    inset 0 0 26px rgba(93, 210, 255, 0.12),
    0 0 20px rgba(93, 210, 255, 0.08);
  opacity: 0;
  animation: cosmic-ring-awake 0.9s ease-out 1.84s forwards;
}

.cosmic-gate404__event-horizon {
  position: absolute;
  left: 50%;
  top: 50%;
  z-index: 4;
  width: 58%;
  aspect-ratio: 1;
  overflow: hidden;
  border-radius: 50%;
  opacity: 0;
  transform: translate(-50%, -50%) scale(0.06);
  background:
    radial-gradient(circle at 44% 43%, rgba(255, 255, 255, 0.98) 0 7%, rgba(220, 250, 255, 0.92) 8% 16%, rgba(93, 210, 255, 0.78) 29%, rgba(53, 96, 224, 0.58) 54%, rgba(4, 8, 32, 0.08) 72%),
    conic-gradient(from 45deg, rgba(92, 224, 255, 0.55), rgba(92, 78, 240, 0.34), rgba(224, 250, 255, 0.68), rgba(92, 224, 255, 0.55));
  box-shadow:
    0 0 42px rgba(93, 210, 255, 0.62),
    0 0 92px rgba(53, 112, 255, 0.34),
    inset 0 0 44px rgba(255, 255, 255, 0.4);
  animation:
    cosmic-horizon-open 1.45s cubic-bezier(0.16, 1, 0.3, 1) 2.55s forwards,
    cosmic-horizon-pulse 4.4s ease-in-out 4.1s infinite;
}

.cosmic-gate404__horizon-swirl,
.cosmic-gate404__horizon-grid {
  position: absolute;
  inset: -18%;
  border-radius: 50%;
  pointer-events: none;
}

.cosmic-gate404__horizon-swirl {
  background: conic-gradient(
    from 0deg,
    transparent,
    rgba(255, 255, 255, 0.52),
    transparent,
    rgba(70, 195, 255, 0.44),
    transparent
  );
  opacity: 0.5;
  mix-blend-mode: screen;
  animation: cosmic-horizon-spin 5.8s linear 2.85s infinite;
}

.cosmic-gate404__horizon-grid {
  inset: 0;
  background:
    linear-gradient(rgba(255, 255, 255, 0.09) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.06) 1px, transparent 1px);
  background-size: 9px 9px;
  opacity: 0.2;
  mix-blend-mode: screen;
  animation: cosmic-pixel-drift 2.2s steps(5) 3.8s infinite;
}

.cosmic-gate404__kawoosh {
  position: absolute;
  left: 50%;
  top: 50%;
  z-index: 7;
  width: 34%;
  aspect-ratio: 1;
  border-radius: 50%;
  opacity: 0;
  transform: translate(-50%, -50%) scale(0.08);
  background:
    radial-gradient(circle, rgba(255, 255, 255, 0.98) 0 14%, rgba(130, 232, 255, 0.76) 15% 34%, rgba(61, 124, 255, 0.26) 48%, transparent 70%);
  mix-blend-mode: screen;
  animation: cosmic-kawoosh 0.95s ease-out 2.62s both;
}

.cosmic-gate404__kawoosh::after {
  content: '';
  position: absolute;
  inset: -34%;
  border-radius: 50%;
  border: 2px solid rgba(190, 244, 255, 0.42);
  filter: blur(1px);
}

.cosmic-gate404__segment {
  position: absolute;
  left: 50%;
  top: 50%;
  z-index: 6;
  width: var(--segment-width);
  height: var(--segment-height);
  opacity: 0;
  transform-origin: center;
  transform:
    translate(calc(-50% + var(--start-x)), calc(-50% + var(--start-y)))
    rotate(var(--start-rot))
    scale(0.25);
  animation: cosmic-segment-assemble 1.55s cubic-bezier(0.2, 0.9, 0.22, 1.18) var(--assemble-delay) both;
}

.cosmic-gate404__segment-shell,
.cosmic-gate404__segment-light {
  position: absolute;
  border-radius: 999px;
}

.cosmic-gate404__segment-shell {
  inset: 0;
  background:
    linear-gradient(180deg, rgba(223, 248, 255, 0.46), rgba(26, 48, 94, 0.9)),
    linear-gradient(90deg, rgba(5, 10, 25, 0.96), rgba(43, 92, 146, 0.96), rgba(5, 10, 25, 0.96));
  border: 1px solid rgba(153, 226, 255, 0.26);
  box-shadow:
    0 0 0 1px rgba(7, 15, 35, 0.88),
    7px 8px 0 rgba(2, 7, 20, 0.32),
    0 0 14px rgba(56, 190, 255, 0.12);
}

.cosmic-gate404__segment-light {
  left: 50%;
  top: 17%;
  width: 44%;
  height: 66%;
  transform: translateX(-50%);
  background: linear-gradient(180deg, #effcff, #62d4ff 48%, #237dff);
  opacity: 0.06;
  box-shadow: 0 0 0 rgba(87, 210, 255, 0);
  animation:
    cosmic-segment-ignite 1.25s ease-out calc(1.75s + var(--ignite-delay)) both,
    cosmic-segment-flicker 2.8s ease-in-out calc(3.4s + var(--ignite-delay)) infinite;
}

.cosmic-gate404__ignition-sweep {
  position: absolute;
  inset: 1%;
  z-index: 10;
  border-radius: 50%;
  opacity: 0;
  background: conic-gradient(
    from -60deg,
    transparent 0 66%,
    rgba(255, 255, 255, 0.86) 69%,
    rgba(89, 213, 255, 0.42) 73%,
    transparent 78% 100%
  );
  mask: radial-gradient(circle, transparent 0 70%, black 71% 78%, transparent 79%);
  animation: cosmic-ignition-sweep 1.7s ease-out 1.85s both;
}

.cosmic-gate404__foreground-glow {
  position: absolute;
  left: 62%;
  top: 46%;
  z-index: 6;
  width: min(48vw, 620px);
  height: min(20vw, 250px);
  border-radius: 50%;
  pointer-events: none;
  background: rgba(99, 210, 255, 0.16);
  filter: blur(42px);
  transform: translate(-50%, -50%) rotate(-12deg);
  opacity: 0;
  animation: cosmic-shadow-awake 1.1s ease-out 2.8s forwards;
}

.cosmic-gate404__scanline {
  position: absolute;
  inset: 0;
  z-index: 20;
  pointer-events: none;
  background: linear-gradient(
    180deg,
    transparent,
    rgba(255, 255, 255, 0.032),
    transparent
  );
  background-size: 100% 8px;
  opacity: 0.23;
  mix-blend-mode: screen;
  animation: cosmic-scanline 7s linear infinite;
}

.cosmic-gate404__copy {
  display: flex;
  justify-content: center;
  margin-top: clamp(20px, 3vw, 34px);
  text-align: center;
}

.cosmic-gate404__copy :deep(h1) {
  margin: 0;
}

@keyframes cosmic-segment-assemble {
  0% {
    opacity: 0;
    transform:
      translate(calc(-50% + var(--start-x)), calc(-50% + var(--start-y)))
      rotate(var(--start-rot))
      scale(0.25);
  }

  62% {
    opacity: 1;
  }

  78% {
    transform:
      translate(-50%, -50%)
      rotate(var(--angle))
      translateY(calc(var(--gate-radius) - 10px))
      scale(1.08);
  }

  100% {
    opacity: 1;
    transform:
      translate(-50%, -50%)
      rotate(var(--angle))
      translateY(var(--gate-radius))
      scale(1);
  }
}

@keyframes cosmic-segment-ignite {
  0% {
    opacity: 0.06;
    box-shadow: 0 0 0 rgba(87, 210, 255, 0);
  }

  38% {
    opacity: 1;
    box-shadow:
      0 0 10px rgba(145, 234, 255, 0.95),
      0 0 26px rgba(57, 190, 255, 0.66);
  }

  100% {
    opacity: 0.74;
    box-shadow:
      0 0 8px rgba(145, 234, 255, 0.72),
      0 0 19px rgba(57, 190, 255, 0.4);
  }
}

@keyframes cosmic-segment-flicker {
  0%,
  100% {
    opacity: 0.62;
  }

  50% {
    opacity: 0.94;
  }
}

@keyframes cosmic-ring-awake {
  from {
    opacity: 0;
    filter: brightness(0.8);
  }

  to {
    opacity: 1;
    filter: brightness(1);
  }
}

@keyframes cosmic-ring-hum {
  0%,
  100% {
    filter: drop-shadow(0 0 8px rgba(69, 190, 255, 0.18));
  }

  50% {
    filter: drop-shadow(0 0 20px rgba(69, 190, 255, 0.38));
  }
}

@keyframes cosmic-horizon-open {
  0% {
    opacity: 0;
    filter: blur(12px) brightness(1.2);
    transform: translate(-50%, -50%) scale(0.06);
  }

  42% {
    opacity: 1;
    filter: blur(2px) brightness(1.4);
    transform: translate(-50%, -50%) scale(1.16);
  }

  72% {
    transform: translate(-50%, -50%) scale(0.96);
  }

  100% {
    opacity: 1;
    filter: blur(0) brightness(1);
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
    filter: brightness(1.16);
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
    opacity: 0.86;
    transform: translate(-50%, -50%) scale(1.5);
  }

  100% {
    opacity: 0;
    transform: translate(-50%, -50%) scale(2.35);
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
    transform: translate(var(--particle-end-x), var(--particle-end-y)) scale(0.25);
  }
}

@keyframes cosmic-star-twinkle {
  0%,
  100% {
    transform: scale(0.75);
    opacity: calc(var(--star-opacity) * 0.62);
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
    transform: translate(9px, 9px);
  }
}

@keyframes cosmic-ignition-sweep {
  0% {
    opacity: 0;
    transform: rotate(-45deg);
  }

  20% {
    opacity: 0.9;
  }

  100% {
    opacity: 0;
    transform: rotate(295deg);
  }
}

@keyframes cosmic-shadow-awake {
  from {
    opacity: 0;
    transform: translate(-50%, -50%) rotate(-12deg) scale(0.82);
  }

  to {
    opacity: 1;
    transform: translate(-50%, -50%) rotate(-12deg) scale(1);
  }
}

@keyframes cosmic-gate-idle {
  0%,
  100% {
    transform: rotateX(5deg) rotateY(-52deg) rotateZ(-8deg) translate3d(0, 0, 0);
  }

  50% {
    transform: rotateX(6deg) rotateY(-50deg) rotateZ(-7deg) translate3d(0, -4px, 0);
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

@media (max-width: 720px) {
  .cosmic-gate404 {
    --gate-size: clamp(280px, 88vw, 350px);
    --gate-radius: -121px;
    --segment-width: 6px;
    --segment-height: 28px;

    width: min(100%, 420px);
  }

  .cosmic-gate404__scene {
    height: 350px;
    border-radius: 28px;
  }

  .cosmic-gate404__gate-shell {
    left: 50%;
    top: 45%;
  }

  .cosmic-gate404__particle {
    left: 50%;
    top: 45%;
  }

  .cosmic-gate404__foreground-glow {
    left: 50%;
    top: 45%;
    width: 310px;
    height: 150px;
  }

  .cosmic-gate404__planet {
    left: -130px;
    bottom: -145px;
    width: 300px;
    opacity: 0.42;
  }

  .cosmic-gate404__nebula--one {
    left: 18%;
    width: 260px;
  }

  .cosmic-gate404__nebula--two {
    right: -20%;
    width: 260px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .cosmic-gate404__star,
  .cosmic-gate404__particle,
  .cosmic-gate404__gate-shadow,
  .cosmic-gate404__gate-plane,
  .cosmic-gate404__depth-echo,
  .cosmic-gate404__ring,
  .cosmic-gate404__event-horizon,
  .cosmic-gate404__horizon-swirl,
  .cosmic-gate404__horizon-grid,
  .cosmic-gate404__kawoosh,
  .cosmic-gate404__segment,
  .cosmic-gate404__segment-light,
  .cosmic-gate404__ignition-sweep,
  .cosmic-gate404__foreground-glow,
  .cosmic-gate404__scanline {
    animation: none !important;
  }

  .cosmic-gate404__particle,
  .cosmic-gate404__kawoosh,
  .cosmic-gate404__ignition-sweep,
  .cosmic-gate404__scanline {
    display: none;
  }

  .cosmic-gate404__gate-shadow,
  .cosmic-gate404__depth-echo,
  .cosmic-gate404__ring,
  .cosmic-gate404__event-horizon,
  .cosmic-gate404__segment,
  .cosmic-gate404__foreground-glow {
    opacity: 1;
  }

  .cosmic-gate404__gate-plane {
    transform: rotateX(5deg) rotateY(-52deg) rotateZ(-8deg);
  }

  .cosmic-gate404__segment {
    transform:
      translate(-50%, -50%)
      rotate(var(--angle))
      translateY(var(--gate-radius))
      scale(1);
  }

  .cosmic-gate404__segment-light {
    opacity: 0.74;
  }

  .cosmic-gate404__event-horizon {
    filter: none;
    transform: translate(-50%, -50%) scale(1);
  }
}
</style>