<script setup>
const SEGMENT_COUNT = 56

function noise(seed) {
  const value = Math.sin(seed * 12.9898 + 78.233) * 43758.5453
  return value - Math.floor(value)
}

const segments = Array.from({ length: SEGMENT_COUNT }, (_, index) => {
  const angle = index * 360 / SEGMENT_COUNT
  // Sample a single upper-left key light in gate space, even as each plate turns.
  const incidence = (1 + Math.cos((angle + 48) * Math.PI / 180)) / 2
  return {
    anchor: index % 7 === 0,
    style: {
      '--angle': angle + 'deg',
      '--steel': (27 + incidence * 38).toFixed(1) + '%',
      '--arrival': (0.08 + index % 28 * 0.024).toFixed(3) + 's',
      '--strike': (1.67 + index * 0.021).toFixed(3) + 's',
    },
  }
})

const particles = Array.from({ length: 22 }, (_, index) => ({
  '--bearing': (index * 137.508).toFixed(2) + 'deg',
  '--arrival': (0.12 + noise(index + 30) * 1.15).toFixed(2) + 's',
  '--duration': (1.12 + noise(index + 60) * 0.6).toFixed(2) + 's',
}))

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
      <span v-for="(star, index) in stars" :key="index" class="star" :style="star" />
      <div class="orbital-track" />
      <div class="moon" />

      <div class="gate-shell">
        <span v-for="(particle, index) in particles" :key="index" class="mote" :style="particle" />
        <div class="gate-plane">
          <div class="housing-back annulus" />
          <div class="housing-side annulus" />
          <div class="housing-face annulus" />
          <div class="aperture-well" />
          <div class="cosmic-gate404__event-horizon">
            <div class="horizon-current" />
            <div class="horizon-reflection" />
          </div>
          <div class="aperture-lip annulus" />

          <span
            v-for="(segment, index) in segments" :key="index"
            class="cosmic-gate404__segment" :class="{ anchor: segment.anchor }" :style="segment.style"
          >
            <span class="plate" />
            <span class="conduit" />
          </span>
          <div class="ignition-wave" />
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
  background:
    radial-gradient(ellipse at 54% 54%, #1537527a, transparent 53%),
    url('../assets/gate-nebula.webp') center / cover,
    linear-gradient(155deg, #0b1121, #080d1c 71%);
  /* Let the observatory sky fall away into the page behind the message. */
  mask-image: linear-gradient(to bottom, transparent, black 8%, black 88%, transparent),
    linear-gradient(to right, transparent, black 10%, black 90%, transparent);
  mask-composite: intersect;
}

.star, .mote { position: absolute; pointer-events: none; }
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

.orbital-track {
  position: absolute;
  width: 102%;
  height: 57%;
  left: -9%;
  top: 31%;
  border: 1px solid #92aace22;
  border-radius: 50%;
  transform: rotate(-16deg);
  mask-image: linear-gradient(72deg, transparent 7%, black 25%, transparent 46%, transparent 62%, black, transparent);
}
.moon {
  position: absolute;
  left: 16%;
  top: 57%;
  width: clamp(27px, 5cqw, 65px);
  aspect-ratio: 1;
  border-radius: 50%;
  background: radial-gradient(ellipse at 67% 78%, #0b1021 42%, #162235 65%, #41536a 81%, #b5a68e 95%);
  box-shadow: -1px -1px 1px #c2bdaf7a, 0 0 18px #7c99c215;
}

.gate-shell {
  --gate-size: min(86cqw, 92cqh, 530px);
  --radius: calc(var(--gate-size) * -.407);
  position: absolute;
  width: var(--gate-size);
  aspect-ratio: 1;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  perspective: 1250px;
}
.gate-shell::before {
  content: '';
  position: absolute;
  inset: -6% -20%;
  background: radial-gradient(ellipse closest-side, #3679a849 15%, #21669624 57%, transparent 100%);
}
.gate-plane {
  position: absolute;
  inset: 0;
  transform: rotateZ(-13deg) rotateY(-32deg) rotateX(12deg);
}

.annulus {
  position: absolute;
  border-radius: 50%;
  mask-image: radial-gradient(closest-side, transparent var(--bore), black calc(var(--bore) + .5%));
}
.housing-back, .housing-side, .housing-face {
  inset: 3%;
  --bore: 70%;
}
.housing-back {
  translate: 5.6% 2.7%;
  border: 1px solid #536a7a;
  background: conic-gradient(from -45deg, #9aaeba, #283449 22%, #0b1020 43%, #344759 66%, #899ca5 88%, #9aaeba);
}
.housing-side {
  translate: 2.5% 1%;
  border: 1px solid #879eac;
  background:
    repeating-conic-gradient(from -1deg, transparent 0deg 3.05deg, #060c19b3 3.16deg 3.55deg),
    conic-gradient(from -50deg, #a6b7b9, #384d60 19%, #233144 33%, #0e1725 51%, #48566b 76%, #a6b7b9);
}
.housing-face {
  border: 1px solid #92a8b7;
  background:
    radial-gradient(closest-side, transparent 91.5%, #0b1421 92% 93.2%, #adc2c488 93.6%, transparent 94.2% 96%, #080f1d 96.6% 97.7%, #8096a4 98.2%, transparent 99%),
    conic-gradient(from -45deg, #b7c5c5, #50687b 13%, #24374c 28%, #566579 43%, #172a41 59%, #697c89 81%, #b7c5c5);
}
.aperture-well {
  position: absolute;
  inset: 14.5%;
  border-radius: 50%;
  background: radial-gradient(ellipse at 55% 44%, #16273d, #071324 59%, #173148 86%, #081525);
  box-shadow: inset 4px 5px 12px #020710b0;
}
.cosmic-gate404__event-horizon {
  position: absolute;
  inset: 15%;
  overflow: hidden;
  isolation: isolate;
  border-radius: 50%;
  background: #142b45;
}
.horizon-current, .horizon-reflection {
  position: absolute;
  border-radius: 50%;
}
.horizon-current {
  inset: -4%;
  background: url('../assets/gate-horizon.webp') center / cover;
  filter: brightness(1.18);
}
.horizon-reflection {
  inset: 0;
  box-shadow: inset 3px 4px 12px #041023a8, inset -2px -2px 7px #a0e9fa61;
  background: radial-gradient(ellipse at 27% 65%, #8ce9ff1c, transparent 48%);
}
.aperture-lip {
  --bore: 91%;
  inset: 13%;
  background:
    radial-gradient(closest-side, transparent 90.5%, #b6f4ff 91.5%, #488da3 92.4%, #142d42 93.6%, transparent 95%, #8da7af66 96%, transparent 97%, #051220 99%),
    conic-gradient(from -50deg, #101d31, #44627a, #85bdc7 38%, #264957 66%, #101d31);
}
/* Light from the approaching wave catches the machined faces nearest the bore. */
.gate-plane::after {
  content: '';
  position: absolute;
  z-index: 2;
  inset: 3%;
  border-radius: 50%;
  background: conic-gradient(transparent 12%, #487ca433 28%, transparent 47%, #65d3e46b 65%, #b4f6ffb8 78%, #5b9ab964 88%, transparent);
  mask-image: radial-gradient(closest-side, transparent 71%, black 74%, #0009 78%, transparent 87%);
}
.cosmic-gate404__event-horizon::after {
  content: '';
  position: absolute;
  inset: 0;
  opacity: 0;
  border-radius: 50%;
  background: radial-gradient(ellipse at 36% 50%, #bbf9ff55, transparent 55%);
  box-shadow: inset 0 0 2px 2px #d5fbff, inset 2px 0 16px 5px #70d7f3;
}

.cosmic-gate404__segment {
  position: absolute;
  top: 50%;
  left: 50%;
  width: calc(var(--gate-size) * .043);
  height: calc(var(--gate-size) * .096);
  transform: translate(-50%, -50%) rotate(var(--angle)) translateY(var(--radius));
}
.plate {
  position: absolute;
  inset: 0;
  clip-path: polygon(5% 3%, 89% 0, 100% 10%, 87% 91%, 73% 100%, 16% 96%, 5% 82%, 0 15%);
  background:
    linear-gradient(103deg, #e0eef194, transparent 10% 76%, #132033a6 80% 91%, #a8babc9c 95%),
    linear-gradient(to bottom, #dcdfcf 0%, hsl(205 13% var(--steel)) 6% 17%, #1e3143 19% 24%, hsl(207 19% var(--steel)) 27%, #35475a 67%, #162b40 83%, #6593a1 88%, #132234 94%);
}
.plate::before, .plate::after {
  content: '';
  position: absolute;
}
.plate::before {
  left: 17%;
  right: 24%;
  top: 27%;
  height: 42%;
  border-top: 1px solid #f2f1de66;
  border-left: 1px solid #c1d5da4d;
  background: linear-gradient(132deg, #b7bfc636, #14273580 76%);
  clip-path: polygon(0 0, 100% 0, 76% 100%, 12% 100%);
}
.plate::after {
  inset: 10% 12% auto 14%;
  height: 3%;
  background: #101b27aa;
}
.conduit {
  position: absolute;
  left: 25%;
  right: 25%;
  bottom: 14%;
  height: 6%;
  border-radius: 1px;
  background: #a6e4ed;
  box-shadow: 0 0 4px #58c7e7ab;
}
.anchor { z-index: 1; }
.anchor .plate {
  inset: -8% -11% -6%;
  background:
    linear-gradient(100deg, #e5d6b6aa, transparent 14% 70%, #0c1823c9 76% 85%, #829299 96%),
    linear-gradient(to bottom, #aa9672 0% 5%, #5e676c 7% 18%, #283745 20% 24%, #809095 28%, #354b5d 66%, #243445 76%, #a28d6e 81% 88%, #182d40 92%);
}
.anchor .conduit { left: 36%; right: 35%; height: 21%; bottom: 24%; background: #c9f5f9; }
.ignition-wave {
  position: absolute;
  inset: 4%;
  border-radius: 50%;
  opacity: 0;
  background: conic-gradient(transparent 0deg 319deg, #6edfff40 339deg, #d6fbffcc 357deg, transparent);
  mask-image: radial-gradient(closest-side, transparent 71%, black 73%, transparent 78%, transparent 92%, black 93%, transparent 98%);
}

.mote {
  top: 50%;
  left: 50%;
  width: 1.5px;
  height: 4px;
  border-radius: 50%;
  background: #a9e4ef;
  opacity: 0;
}

.cosmic-gate404__copy { position: relative; text-align: center; }

@media (max-width: 720px) {
  .cosmic-gate404__scene { height: clamp(225px, 71vw, 350px); }
  .moon { left: 6%; top: 65%; width: 22px; }
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

/* The base pose is the lit, assembled gate, including when a running preference changes. */
@media (prefers-reduced-motion: no-preference) {
  .cosmic-gate404__segment {
    animation: assemble 1.35s cubic-bezier(.18,.74,.2,1) var(--arrival) backwards;
  }
  .housing-back, .housing-side, .housing-face, .aperture-well, .aperture-lip {
    animation: resolve-housing 1.05s ease-out .61s backwards;
  }
  .gate-plane::after { animation: reflection-awake 1.02s ease-out 2.65s backwards; }
  .conduit { animation: ignite .48s ease-out var(--strike) backwards; }
  .ignition-wave { animation: sweep 1.18s linear 1.68s; }
  .cosmic-gate404__event-horizon { animation: open-aperture 1.27s cubic-bezier(.25,.05,.23,1) 2.5s backwards; }
  .cosmic-gate404__event-horizon::after { animation: wave-front 1.27s ease-out 2.5s; }
  .horizon-current { animation: tide 18s ease-in-out 3.8s infinite alternate; }
  .horizon-reflection { animation: afterglow 8s ease-in-out 4s infinite alternate; }
  .mote { animation: accrete var(--duration) ease-in var(--arrival) backwards; }
  .star:nth-child(13n) { animation: scintillate 6s ease-in-out infinite alternate; }
  .star:nth-child(26n) { animation-delay: -3s; }
}
@keyframes assemble {
  from {
    opacity: 0;
    transform: translate(-50%, -50%) rotate(calc(var(--angle) - 28deg))
      translateY(calc(var(--radius) * 1.57)) rotate(-29deg) scale(.68);
  }
  35% { opacity: 1; }
  to { transform: translate(-50%, -50%) rotate(var(--angle)) translateY(var(--radius)); }
}
@keyframes resolve-housing { from { opacity: .045; } to { opacity: 1; } }
@keyframes ignite { from { opacity: .07; } 65% { opacity: 1; } }
@keyframes sweep {
  0% { opacity: 0; transform: rotate(0); }
  14%, 78% { opacity: .86; }
  100% { opacity: 0; transform: rotate(360deg); }
}
@keyframes open-aperture {
  0% { opacity: 0; transform: scale(.09, .025); }
  24% { opacity: .93; }
  66% { transform: scale(1.018); }
  100% { opacity: 1; transform: scale(1); }
}
@keyframes wave-front { 0% { opacity: 0; } 22% { opacity: .95; } 100% { opacity: 0; } }
@keyframes reflection-awake { from { opacity: 0; } to { opacity: 1; } }
@keyframes tide {
  from { transform: rotate(0) scale(1); }
  to { transform: translate(.6%, -.4%) rotate(3deg) scale(1.025); }
}
@keyframes afterglow { from { opacity: .65; } to { opacity: 1; } }
@keyframes accrete {
  0% { opacity: 0; transform: rotate(calc(var(--bearing) - 19deg)) translateY(calc(var(--radius) * 1.58)); }
  36% { opacity: .72; }
  100% { opacity: 0; transform: rotate(var(--bearing)) translateY(calc(var(--radius) * .87)) scale(.38); }
}
@keyframes scintillate { from { opacity: .42; } to { opacity: .86; } }
</style>
