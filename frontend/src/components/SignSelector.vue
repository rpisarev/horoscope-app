<script setup>
const props = defineProps({ modelValue: String })
const emit = defineEmits(['update:modelValue', 'change'])

const SIGNS = [
  'aries','taurus','gemini','cancer','leo','virgo',
  'libra','scorpio','sagittarius','capricorn','aquarius','pisces','ophiuchus'
]

function update(value) {
  emit('update:modelValue', value)
  emit('change', value)
}
</script>

<template>
  <select class="border p-1 rounded" :value="props.modelValue" @change="update($event.target.value)">
    <option v-for="s in SIGNS" :key="s" :value="s">{{ s }}</option>
  </select>
</template>
