<script setup>
import { onBeforeUnmount, onMounted, ref, useId } from 'vue'

const deviceId = useId()
const SEGMENT_COUNT = 80
const opening = ref(true)
let motionPreference

function skipOpeningOnReduce() {
  if (motionPreference?.matches) opening.value = false
}

onMounted(() => {
  motionPreference = window.matchMedia?.('(prefers-reduced-motion: reduce)')
  skipOpeningOnReduce()
  motionPreference?.addEventListener('change', skipOpeningOnReduce)
})
onBeforeUnmount(() => motionPreference?.removeEventListener('change', skipOpeningOnReduce))

function noise(seed) {
  const value = Math.sin(seed * 12.9898 + 78.233) * 43758.5453
  return value - Math.floor(value)
}

const segments = Array.from({ length: SEGMENT_COUNT }, (_, index) => {
  const angle = index * 360 / SEGMENT_COUNT
  // The same casting is exposed to one distant light as it goes around the rim.
  const light = (1 + Math.cos((angle + 40) * Math.PI / 180)) / 2
  return {
    placement: `rotate(${angle} 256 256) translate(256 10)`,
    material: {
      '--face': (31 + light * 27).toFixed(1) + '%',
      '--edge': (49 + light * 32).toFixed(1) + '%',
      '--charge-delay': (0.48 + index * 0.017).toFixed(3) + 's',
    },
  }
})

const stars = Array.from({ length: 84 }, (_, index) => ({
  left: (noise(index + 1500) * 100).toFixed(2) + '%',
  top: (noise(index + 1600) * 100).toFixed(2) + '%',
  '--size': (0.7 + noise(index + 1700) ** 3 * 2).toFixed(2) + 'px',
  '--shine': (0.22 + noise(index + 1900) * 0.54).toFixed(2),
}))
</script>

<template>
  <section class="cosmic-gate404">
    <div class="cosmic-gate404__scene" aria-hidden="true">
      <div class="gate-sky">
        <span v-for="(star, index) in stars" :key="index" class="star" :style="star" />
      </div>
      <div class="gate-shell" :class="{ 'is-opening': opening }">
        <div class="gate-plane">
          <div class="aperture-light" />
          <div class="cosmic-gate404__event-horizon">
            <div class="water-phase" />
            <div class="return-wake" @animationend.self="opening = false" />
          </div>

          <svg class="device-ring" viewBox="0 0 512 512" focusable="false">
            <defs>
              <!-- One stepped, bevelled device, including its recessed access panel. -->
              <g :id="deviceId" stroke-linejoin="round">
                <path d="M-6 1 4.9 0 7.2 2.8 7.3 9 6.2 10 6.1 18.8 3.9 21.5 -3.5 22 -6.1 19.2 -6.3 13 -7.5 11.5 -7.5 3Z"
                  fill="hsl(211 20% 19%)" stroke="#101c27" stroke-width=".65" />
                <path d="M-6.5 2.6 -4.7 .6 4.6 .5 6 2.2 4.6 4.7 -4.8 5.4Z" fill="hsl(204 16% var(--edge))" />
                <path d="M-5.7 5.3 4.8 4.5 5.1 10.9 3.9 11.6 3.8 18.2 -3.7 19.2 -5.2 17.5Z"
                  fill="hsl(206 16% var(--face))" />
                <path d="M-6.2 4.8 -4.8 5.4 -4.1 18.2 -3.3 20 -5.4 18.4Z" fill="hsl(201 15% var(--edge))" />
                <path d="M-2.9 7 2.7 6.7 2.5 13.3 -2.7 13.8Z" fill="#273848" />
                <path d="m-2.3 7.4 4.6-.3 -.1 3.8 -4.4.4Z" fill="hsl(203 16% var(--face))" />
                <path d="m-3.5 16 6.5-.5 m-6.2 2.2 5.8-.5" fill="none" stroke="#182b39" stroke-width=".68" />
                <path d="m-3.8 19.8 7.5-.7 -1.4 1.2 -4.8.6Z" fill="#97b8c6" />
              </g>
            </defs>
            <g class="castings">
              <g v-for="device in segments" :key="device.placement" class="cosmic-gate404__segment"
                :transform="device.placement" :style="device.material">
                <!-- The narrow electrical bridge crosses the open gap to the next unit. -->
                <path class="coupling" d="m5.5 10.5 3.3 .2 2 -.7 2.3 .5" />
                <use :href="'#' + deviceId" />
                <path class="charge-arc" d="m-7.3 10.5 2.9-.9 1.4 1.3 2.1-3.8 1.6.9 .8-2.1 1.5 3.7 2.1-.8 1.3 1.7 2.6.2 2-.9 2.4.6" />
              </g>
            </g>
          </svg>
          <div class="kawoosh"><div class="wave-frames" /></div>
        </div>
      </div>
    </div>

    <div v-if="$slots.default" class="cosmic-gate404__copy"><slot /></div>
  </section>
</template>

<style scoped>
.cosmic-gate404 {
  width: min(100%, 1240px);
  margin-inline: auto;
  isolation: isolate;
}

.cosmic-gate404__scene {
  position: relative;
  container-type: size;
  height: clamp(340px, 56svh, 570px);
  overflow: hidden;
  pointer-events: none;
}
.gate-sky {
  position: absolute;
  inset: 0;
  background:
    linear-gradient(#070b1960, #070b1960),
    #070b19 url('../assets/gate-nebula.webp') center / cover;
  background-blend-mode: normal, lighten;
  mask-image: radial-gradient(ellipse closest-side, black 35%, #000e 57%, #0007 78%, transparent);
}

.star { position: absolute; }
.star {
  width: var(--size);
  height: var(--size);
  border-radius: 50%;
  background: #d4e8f4;
  opacity: var(--shine);
}
.star:nth-child(13n) {
  width: 3px;
  height: 3px;
  background: #f1e8cd;
  box-shadow: 0 0 6px 1px #a1d6ff70;
}
.star:nth-child(13n)::after {
  content: '';
  position: absolute;
  inset: -3px 1px;
  background: linear-gradient(transparent, #dfedff, transparent);
}

.gate-shell {
  --breach-at: 1.84s;
  --flight: 1.72s;
  --return-at: calc(var(--breach-at) + var(--flight) * .68);
  --diameter: min(86cqw, 92cqh, 530px);
  position: absolute;
  width: var(--diameter);
  aspect-ratio: 1;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  perspective: calc(3.2 * var(--diameter));
}
.gate-plane {
  position: absolute;
  inset: 0;
  /* The roll keeps the projected normal on the existing wave's aperture-to-crest axis. */
  transform: rotateY(-32deg) rotateX(12deg) rotateZ(-10.9deg);
}
.device-ring {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
.castings { filter: drop-shadow(2.5px 1.4px 0 #344856); }
.coupling, .charge-arc {
  fill: none;
  stroke-linejoin: round;
}
.coupling {
  stroke: #85c8f6;
  stroke-width: 1.45;
  opacity: .88;
}
.charge-arc {
  stroke: #d6f7ff;
  stroke-width: 1.7;
  opacity: 0;
}

/* The membrane meets the inward-facing ends of the modules at r=225 in the 512-unit plane. */
.cosmic-gate404__event-horizon {
  position: absolute;
  inset: 6.05%;
  overflow: hidden;
  border-radius: 50%;
  background: #77a9bd url('../assets/supergate-water.webp') center / cover;
  box-shadow: 0 0 2px #afecffb3, 0 0 12px 2px #5ea3ca50, 0 0 33px 4px #5189b025;
}
.water-phase {
  position: absolute;
  inset: 0;
  background: url('../assets/supergate-water-shimmer.webp') center / cover;
  opacity: 0;
}
.aperture-light, .return-wake {
  position: absolute;
  display: none;
  border-radius: 50%;
  opacity: 0;
}
.aperture-light {
  inset: 4.5%;
  background: radial-gradient(closest-side, transparent 78%, #4fa8d51c 89%,
    #a6ecff9e 94%, #dbfaff 96%, #86d9fd96 97.5%, transparent 100%);
  box-shadow: 0 0 24px 6px #6bb9ed36;
}
.return-wake {
  inset: 0;
  background: url('../assets/supergate-water-shimmer.webp') center / cover;
  mask-image: radial-gradient(closest-side, transparent 60%, #0008 71%, black 79%, transparent 94%);
  mix-blend-mode: screen;
}
.kawoosh { display: none; }

.cosmic-gate404__copy { position: relative; text-align: center; }

@media (max-width: 720px) {
  .cosmic-gate404__scene { height: clamp(225px, 71vw, 350px); }
}
@media (max-height: 450px) and (orientation: landscape) {
  .cosmic-gate404__scene { height: clamp(186px, 68svh, 254px); }
}
@media (max-height: 450px) and (min-width: 500px) and (orientation: landscape) {
  .cosmic-gate404 {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1.05fr);
    align-items: center;
    gap: 1vw;
  }
}

/* The assembled devices never move. The base membrane stays active after the
   one-shot incoming wormhole finishes and whenever reduced motion is selected. */
@media (prefers-reduced-motion: no-preference) {
  .is-opening .coupling { animation: energize .58s ease-out var(--charge-delay) backwards; }
  .is-opening .charge-arc { animation: arc-over .48s ease-out var(--charge-delay); }
  .is-opening .aperture-light {
    display: block;
    animation: power-spill calc(var(--breach-at) + var(--flight)) ease-in-out;
  }
  .is-opening .cosmic-gate404__event-horizon {
    mask-position: center;
    mask-repeat: no-repeat;
    animation: establish .62s ease-out calc(var(--breach-at) + .09s) backwards;
  }
  .is-opening .device-ring { animation: reflected-light var(--flight) ease-in-out var(--breach-at); }
  .is-opening .return-wake {
    display: block;
    animation: returning-water .68s ease-out var(--return-at);
  }
  /* Each 512×448 frame places the aperture at (308, 251), radius 160. Map that
     circle onto the gate's 225-unit aperture; only the water moves between frames. */
  .is-opening .kawoosh {
    --wave-axis: 60.15625% 56.0268%;
    position: absolute;
    display: block;
    visibility: hidden;
    overflow: hidden;
    width: 140.625%;
    height: 123.046875%;
    left: -34.5947%;
    top: -18.9392%;
    mask-position: var(--wave-axis);
    mask-repeat: no-repeat;
    animation: show-wave var(--flight) step-end var(--breach-at),
      breach-front .38s ease-in var(--breach-at);
  }
  .is-opening .wave-frames {
    width: 600%;
    height: 600%;
    background: url('../assets/supergate-wave.webp') 0 0 / 100% 100% no-repeat;
    animation: frame-column calc(var(--flight) / 6) steps(6, end) var(--breach-at) 6,
      frame-row var(--flight) steps(6, end) var(--breach-at);
  }
  .water-phase { animation: ripple 3.8s ease-in-out 3.1s infinite alternate; }
  .star:nth-child(13n) { animation: scintillate 6s ease-in-out infinite alternate; }
  .star:nth-child(26n) { animation-delay: -3s; }
}
@keyframes energize {
  0% { opacity: .58; stroke-width: 1.05; }
  45% { opacity: 1; stroke: #f4fdff; stroke-width: 2.6; }
  100% { opacity: .88; stroke-width: 1.45; }
}
@keyframes arc-over { 0%, 100% { opacity: 0; } 30% { opacity: 1; } }
@keyframes power-spill {
  0%, 14%, 100% { opacity: 0; }
  42% { opacity: .16; }
  54% { opacity: .93; }
  65% { opacity: .55; }
  77% { opacity: .85; }
}
@keyframes establish {
  from, to { mask-image: radial-gradient(ellipse closest-side, black 46%, #000c 62%, transparent 100%); }
  0% { opacity: 0; mask-size: 3% 1%; }
  32% { opacity: .8; mask-size: 70% 48%; }
  100% { opacity: 1; mask-size: 245% 245%; }
}
@keyframes reflected-light {
  0%, 100% { filter: none; }
  22% { filter: brightness(1.15); }
  52% { filter: brightness(1.56); }
}
@keyframes show-wave { from, to { visibility: visible; } }
@keyframes breach-front {
  from, to { mask-image: radial-gradient(ellipse closest-side at var(--wave-axis), black 45%, transparent 100%); }
  from { mask-size: 4% 2%; }
  to { mask-size: 265% 265%; }
}
@keyframes frame-column { from { translate: 0 0; } to { translate: -100% 0; } }
@keyframes frame-row { from { transform: translateY(0); } to { transform: translateY(-100%); } }
@keyframes returning-water {
  0% { opacity: 0; transform: scale(.42,.36); }
  36% { opacity: .57; }
  100% { opacity: 0; transform: scale(1.18,1.14); }
}
@keyframes ripple {
  from { opacity: 0; transform: scale(1); }
  to { opacity: .83; transform: scale(1.006); }
}
@keyframes scintillate { from { opacity: .42; } to { opacity: .86; } }
</style>
