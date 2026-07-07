<script setup lang="ts">
import type { AppItem } from '@/api/types'

defineProps<{ app: AppItem; selected: boolean; playing: boolean }>()
const emit = defineEmits<{ select: []; show: []; toggle: [] }>()

const TYPE_MARK: Record<string, string> = {
  star: '★',
  python: 'py',
  static: '▦',
  panel: '▤',
  live_audio: 'au',
  live_nowplaying: 'np',
  unknown: '·',
}
</script>

<template>
  <li
    class="group flex items-center gap-2.5 border-b border-[#1c0e14] px-3 py-2 text-xs last:border-b-0"
    :class="selected ? 'bg-[#1e0f18]' : 'hover:bg-[#160b12]'"
  >
    <!-- live-on-display indicator -->
    <span class="w-2 shrink-0 text-center text-[8px] text-flame" :class="playing ? 'blink' : 'opacity-0'">●</span>

    <!-- click name to preview -->
    <button
      class="flex-1 truncate text-left uppercase tracking-wide"
      :class="selected ? 'text-core' : 'text-gold'"
      @click="emit('select')"
    >
      {{ app.name }}
    </button>

    <span class="shrink-0 text-[9px] text-dim" :title="app.app_type">{{ TYPE_MARK[app.app_type] ?? '·' }}</span>
    <span v-if="app.priority > 0" class="shrink-0 text-[10px] text-[#ff6a4a]">×{{ app.priority + 1 }}</span>

    <!-- push to physical display (hover-reveal) -->
    <button
      class="shrink-0 text-[9px] uppercase tracking-wider text-dim opacity-0 transition-opacity hover:text-gold group-hover:opacity-100"
      title="Show on the display now"
      @click="emit('show')"
    >
      show
    </button>

    <!-- enable / disable -->
    <button
      class="w-8 shrink-0 text-right text-[10px]"
      :class="app.enabled ? 'text-flame' : 'text-[#7a4a34]'"
      @click="emit('toggle')"
    >
      {{ app.enabled ? 'ON' : 'OFF' }}
    </button>
  </li>
</template>
