<template>
<canvas
  ref="canvas"
  class="fixed inset-0 z-0 pointer-events-none"
></canvas>
</template>
<script setup>
import { ref, onMounted } from 'vue'
const canvas = ref(null)
const stars = []
const speed = 120 // px per second

onMounted(() => {
  const ctx = canvas.value.getContext('2d')
  function resize() {
    canvas.value.width = innerWidth
    canvas.value.height = innerHeight
  }
  resize(); addEventListener('resize', resize)

  setInterval(() => {
    stars.push({
      x: -2, y: Math.random()*innerHeight,
      r: Math.random()*2+1
    })
  }, 250)

  let prev = performance.now()
  function tick(now){
    const dt = (now-prev)/1000; prev=now
    ctx.fillStyle = '#070b19'
    ctx.fillRect(0,0,innerWidth,innerHeight)
    for(let i=stars.length-1;i>=0;i--){
      const s=stars[i]; s.x+=speed*dt
      if(s.x>innerWidth+4) stars.splice(i,1)
      else{
        ctx.fillStyle='#fff'; ctx.beginPath()
        ctx.arc(s.x,s.y,s.r,0,Math.PI*2); ctx.fill()
      }
    }
    requestAnimationFrame(tick)
  }
  requestAnimationFrame(tick)
})
</script>

