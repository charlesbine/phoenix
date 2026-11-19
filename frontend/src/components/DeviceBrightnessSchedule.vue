<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api } from '@/api/client'
import type { BrightnessSchedule, Device } from '@/api/types'

const props = defineProps<{ device: Device }>()
const emit = defineEmits<{ saved: [BrightnessSchedule] }>()

const schedule = ref<BrightnessSchedule>({ enabled: false, mode: 'custom', steps: [] })
const nightEnabled = computed(() =>
  props.device.brightness_schedule?.mode === 'night' && props.device.brightness_schedule.enabled,
)
const scheduleLabel = computed(() => {
  if (nightEnabled.value) return 'Night Mode enabled'
  return props.device.brightness_schedule?.enabled ? 'Custom schedule active' : 'Manual control'
})
const saving = ref(false)
const message = ref('')
const error = ref('')

watch(() => props.device.brightness_schedule, (saved) => {
  schedule.value = {
    enabled: saved?.mode === 'custom' && saved.enabled,
    mode: 'custom',
    steps: saved?.steps.map((step) => ({ ...step })) ?? [],
  }
}, { immediate: true })

function addTime(): void {
  const used = new Set(schedule.value.steps.map((step) => step.time))
  const times = ['07:00', '09:00', '18:00', '23:00']
  const time = times.find((option) => !used.has(option)) ?? ''
  schedule.value.steps.push({ time, brightness: props.device.brightness })
  message.value = ''
}

function toggleNight(): void {
  void save({ enabled: !nightEnabled.value, mode: 'night', steps: props.device.brightness_schedule?.steps ?? [] })
}

async function save(config: BrightnessSchedule): Promise<void> {
  message.value = ''
  error.value = ''
  saving.value = true
  try {
    const saved = await api.setBrightnessSchedule(props.device.id, config)
    emit('saved', saved)
    message.value = 'Schedule saved.'
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="mt-4 border-t border-[#3a2016] pt-3">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h3 class="text-sm font-semibold text-core">Brightness schedule</h3>
        <p class="mt-1 text-xs text-muted">{{ scheduleLabel }}</p>
      </div>
      <button type="button" class="schedule-button border-[#8f4b29]" :disabled="saving" @click="toggleNight">
        {{ nightEnabled ? 'Turn off Night Mode' : 'Use Night Mode' }}
      </button>
    </div>
    <p class="mt-2 text-xs leading-relaxed text-muted">
      Dim to 25% between sunset and sunrise. Off midnight–8 a.m. Monday–Friday
      and 2–9 a.m. on Saturday and Sunday mornings.
    </p>
    <details class="mt-3">
      <summary class="cursor-pointer rounded text-sm text-gold focus-visible:outline-flame">Custom schedule</summary>
      <form class="mt-3 grid max-w-xl grid-cols-1 gap-3" @submit.prevent="save(schedule)" @input="message = ''">
        <label class="flex min-h-9 items-center gap-2 text-xs text-core">
          <input v-model="schedule.enabled" type="checkbox" class="h-4 w-4 accent-[#ff9e3d]" />
          Use custom schedule
        </label>
        <p class="text-xs leading-relaxed text-muted">
          Each level holds until the next scheduled time, including overnight. Set brightness to 0 to turn the panel off.
        </p>
        <fieldset v-for="(step, index) in schedule.steps" :key="index" class="schedule-row rounded border border-[#3a2016] p-2.5">
          <legend class="px-1 text-[11px] text-muted">Time {{ index + 1 }}</legend>
          <label class="grid min-w-0 gap-1 text-xs text-core">
            Start time
            <input v-model="step.time" type="time" required class="schedule-input w-full" />
          </label>
          <label class="grid min-w-0 gap-1 text-xs text-core">
            Brightness (0–255)
            <input v-model.number="step.brightness" type="number" min="0" max="255" required class="schedule-input w-full" />
          </label>
          <button type="button" class="schedule-button" :aria-label="`Remove time ${index + 1}`"
            @click="schedule.steps.splice(index, 1); message = ''">Remove</button>
        </fieldset>
        <div class="flex flex-wrap items-center gap-2">
          <button type="button" class="schedule-button" :disabled="schedule.steps.length >= 24" @click="addTime">Add time</button>
          <button type="submit" class="schedule-button border-[#8f4b29] text-core" :disabled="saving">
            {{ saving ? 'Saving…' : 'Save custom schedule' }}
          </button>
        </div>
      </form>
    </details>
    <p v-if="message" role="status" class="mt-2 text-xs text-gold">{{ message }}</p>
    <p v-if="error" role="alert" class="mt-2 text-xs text-[#ff947b]">{{ error }}</p>
  </div>
</template>

<style scoped>
.schedule-input, .schedule-button {
  min-height: 2.25rem;
  border: 1px solid #3a2016;
  border-radius: 0.25rem;
  background: #120a10;
  color: var(--color-gold, #f4bc71);
  padding: 0.375rem 0.625rem;
  font-size: 0.75rem;
}
.schedule-input { min-width: 0; color-scheme: dark; }
.schedule-button:hover { background: #251009; }
.schedule-button:disabled { opacity: 0.5; }
.schedule-input:focus-visible, .schedule-button:focus-visible { outline: 1px solid #ff9e3d; }
.schedule-row { display: grid; min-width: 0; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto; align-items: end; gap: 0.5rem; }
@media (max-width: 390px) {
  .schedule-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .schedule-row button { grid-column: span 2; justify-self: start; }
}
</style>
