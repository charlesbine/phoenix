<script setup lang="ts">
import phoenix from '@/assets/phoenix.png'

const { size = 26 } = defineProps<{ size?: number }>()
</script>

<template>
  <div class="flex items-center gap-2.5">
    <img
      :src="phoenix"
      alt="Phoenix"
      class="px"
      :style="{ width: size + 'px', height: size + 'px', filter: 'drop-shadow(0 0 10px #ff5a2a66)' }"
    />
    <span
      class="fire font-mono font-bold uppercase"
      :style="{ fontSize: size * 0.72 + 'px', letterSpacing: '0.16em' }"
    >Phoenix</span>
  </div>
</template>
