<script setup lang="ts">
import { computed } from 'vue'
import type { AppItem } from '@/api/types'

const props = defineProps<{ app: AppItem; selected: boolean; playing: boolean }>()
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

const isUnhealthy = computed(() => props.app.health_status === 'unhealthy')
const isSkipped = computed(() => props.app.enabled && props.app.skipped_unhealthy)
const isDownActive = computed(() => props.app.enabled && isUnhealthy.value && !props.app.skipped_unhealthy)
const healthTooltip = computed(() => {
  const parts: string[] = []
  if (props.app.health_reason) parts.push(props.app.health_reason)
  else parts.push('Data ingress down')
  if (isSkipped.value) parts.push('Auto-skipped in rotation')
  else if (isDownActive.value) parts.push('Still in cycle')
  parts.push(`Last healthy: ${props.app.last_healthy_human || 'never'}`)
  return parts.join(' · ')
})
const toggleTooltip = computed(() => {
  if (isSkipped.value) return 'Enabled, auto-skipped while data is down — click to disable'
  return props.app.enabled ? 'Click to disable' : 'Click to enable'
})
</script>

<template>
  <li
    class="group flex items-center gap-2.5 border-b border-[#1c0e14] px-3 py-2 text-xs transition-opacity last:border-b-0"
    :class="[
      selected
        ? 'bg-[#1e0f18]'
        : isSkipped
          ? 'bg-[#13090d]/70 hover:bg-[#190c13]'
          : 'hover:bg-[#160b12]',
      isSkipped
        ? selected
          ? 'border-l-2 border-l-[#e6923a]'
          : 'border-l-2 border-l-[#c87a2a]/80 opacity-70 hover:opacity-95'
        : isDownActive
          ? 'border-l-2 border-l-[#ff5a2a]'
          : isUnhealthy
            ? 'border-l-2 border-l-[#6b2a22]'
            : '',
    ]"
  >
    <!-- live-on-display indicator -->
    <span class="w-2 shrink-0 text-center text-[8px] text-flame" :class="playing ? 'blink' : 'opacity-0'">●</span>

    <!-- click name to preview -->
    <button
      class="flex-1 truncate text-left uppercase tracking-wide"
      :class="
        selected
          ? 'text-core'
          : isSkipped
            ? 'text-muted'
            : isDownActive
              ? 'text-[#ff8a6a]'
              : !app.enabled
                ? 'text-dim'
                : 'text-gold'
      "
      @click="emit('select')"
    >
      {{ app.name }}
    </button>

    <span
      v-if="isSkipped"
      class="shrink-0 rounded border border-[#8a4d22] bg-[#241309] px-1.5 py-0.5 text-[9px] uppercase tracking-wider text-[#f0a552]"
      :title="healthTooltip"
    >
      skipped
    </span>
    <span
      v-else-if="isUnhealthy"
      class="shrink-0 rounded border px-1.5 py-0.5 text-[9px] uppercase tracking-wider"
      :class="
        app.enabled
          ? 'border-[#b3241a] bg-[#2a0a0e] text-[#ff6a4a]'
          : 'border-[#5c2520] bg-[#1a0a0d] text-[#b36858]'
      "
      :title="healthTooltip"
    >
      down
    </span>
    <span class="shrink-0 text-[9px] text-dim" :title="app.app_type">{{ TYPE_MARK[app.app_type] ?? '·' }}</span>
    <span v-if="app.priority > 0" class="shrink-0 text-[10px]" :class="isSkipped ? 'text-dim' : 'text-[#ff6a4a]'">
      ×{{ app.priority + 1 }}
    </span>

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
      class="w-9 shrink-0 text-right text-[10px] transition-colors"
      :class="
        !app.enabled
          ? 'text-[#7a4a34] hover:text-gold'
          : isSkipped
            ? 'text-[#8a5d3b] hover:text-gold'
            : isDownActive
              ? 'text-[#ff6a4a] hover:text-gold'
              : 'text-flame hover:text-core'
      "
      :title="toggleTooltip"
      @click="emit('toggle')"
    >
      {{ !app.enabled ? 'OFF' : isSkipped ? 'HOLD' : 'ON' }}
    </button>
  </li>
</template>
