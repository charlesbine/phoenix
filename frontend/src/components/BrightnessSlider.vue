<script setup lang="ts">
import { ref, watch } from 'vue'

const props = defineProps<{ value: number }>()
const emit = defineEmits<{ commit: [value: number] }>()

const local = ref(props.value)
const dragging = ref(false)

// Keep in sync with polled config, but don't yank the thumb mid-drag.
watch(
  () => props.value,
  (v) => {
    if (!dragging.value) local.value = v
  },
)

function commit() {
  dragging.value = false
  emit('commit', local.value)
}
</script>

<template>
  <div>
    <div class="mb-2 text-[10px] uppercase tracking-[0.18em] text-dim">
      Brightness · <span class="text-gold">{{ local }}</span>
    </div>
    <input
      v-model.number="local"
      type="range"
      min="0"
      max="255"
      class="ember-range w-full"
      @pointerdown="dragging = true"
      @change="commit"
    />
  </div>
</template>

<style scoped>
.ember-range {
  -webkit-appearance: none;
  appearance: none;
  height: 12px;
  background: #1a0d10;
  border: 1px solid #3a2016;
  cursor: pointer;
}
.ember-range::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 14px;
  height: 22px;
  background: #ff9e3d;
  box-shadow: 0 0 11px #ff6a2a;
}
.ember-range::-moz-range-thumb {
  width: 14px;
  height: 22px;
  border: 0;
  background: #ff9e3d;
  box-shadow: 0 0 11px #ff6a2a;
}
</style>
