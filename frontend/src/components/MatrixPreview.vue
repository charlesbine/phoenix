<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { api } from '@/api/client'

const props = defineProps<{ app: string | null; tick: number | string; device?: string; live?: boolean }>()
const emit = defineEmits<{ render: [] }>()

const broken = ref(false)
// Live apps have no rendered webp — show the panel's latest streamed frame.
const src = computed(() => {
  if (!props.app) return null
  const url = props.live && props.device ? api.liveFrameUrl(props.device) : api.frameUrl(props.app)
  return `${url}?t=${encodeURIComponent(props.tick)}`
})

watch(src, () => {
  broken.value = false
})
</script>

<template>
  <div
    class="relative rounded-2xl border-2 border-[#24121c] bg-[#0a0508] p-2.5"
    style="box-shadow: inset 0 0 26px #3a0f06, inset 0 0 0 2px #1c0e14, 0 0 30px -8px rgba(255, 90, 42, 0.4)"
  >
    <div class="relative aspect-square overflow-hidden rounded-lg bg-black">
      <img
        v-if="src && !broken"
        :src="src"
        alt="Matrix preview"
        class="px h-full w-full object-contain"
        @error="broken = true"
      />
      <div v-else class="grid h-full w-full place-items-center px-6 text-center">
        <div>
          <div class="text-[11px] uppercase tracking-widest text-dim">
            {{ app ? 'no frame rendered' : 'no signal' }}
          </div>
          <button
            v-if="app"
            class="mt-3 rounded border border-[#3a2016] px-3 py-1 text-[11px] uppercase tracking-wider text-flame hover:bg-[#251009]"
            @click="emit('render')"
          >
            ⟳ Render preview
          </button>
        </div>
      </div>
      <div
        class="pointer-events-none absolute inset-0"
        style="background: repeating-linear-gradient(0deg, transparent 0 2px, rgba(0, 0, 0, 0.28) 2px 3px); mix-blend-mode: multiply"
      ></div>
    </div>
  </div>
</template>
