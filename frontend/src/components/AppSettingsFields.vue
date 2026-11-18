<script setup lang="ts">
import { useId } from 'vue'
import type { SchemaField } from '@/api/types'

defineProps<{ schema: SchemaField[]; values: Record<string, string> }>()
const emit = defineEmits<{ change: [id: string, value: string] }>()
const prefix = useId()
const inputClass = 'w-full rounded border border-[#3a2016] bg-[#120a10] px-2 py-1.5 text-xs text-gold focus:border-flame focus:outline-none'

function update(id: string, event: Event): void {
  const target = event.target as HTMLInputElement
  emit('change', id, target.type === 'checkbox' ? String(target.checked) : target.value)
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <div v-for="field in schema" :key="field.id">
      <label :for="`${prefix}-${field.id}`" class="mb-1 block text-[10px] uppercase tracking-[0.14em] text-dim">
        {{ field.name ?? field.id }}
      </label>
      <p v-if="field.desc" :id="`${prefix}-${field.id}-description`" class="mb-1 text-[10px] text-muted">
        {{ field.desc }}
      </p>
      <select
        v-if="field.type === 'dropdown'"
        :id="`${prefix}-${field.id}`"
        :aria-describedby="field.desc ? `${prefix}-${field.id}-description` : undefined"
        :value="values[field.id]"
        :class="inputClass"
        @change="update(field.id, $event)"
      >
        <option v-for="option in field.options ?? []" :key="option.value" :value="option.value">{{ option.display }}</option>
      </select>
      <label v-else-if="field.type === 'toggle'" class="flex items-center gap-2 text-xs text-gold">
        <input
          :id="`${prefix}-${field.id}`"
          :aria-describedby="field.desc ? `${prefix}-${field.id}-description` : undefined"
          type="checkbox"
          :checked="values[field.id] === 'true'"
          @change="update(field.id, $event)"
        />
        <span aria-hidden="true">{{ values[field.id] === 'true' ? 'on' : 'off' }}</span>
      </label>
      <input
        v-else
        :id="`${prefix}-${field.id}`"
        :aria-describedby="field.desc ? `${prefix}-${field.id}-description` : undefined"
        :type="field.type === 'color' || field.type === 'number' ? field.type : 'text'"
        :step="field.step"
        :value="values[field.id] || (field.type === 'color' ? '#000000' : '')"
        :class="field.type === 'color' ? 'h-8 w-16 rounded border border-[#3a2016] bg-[#120a10]' : inputClass"
        @input="update(field.id, $event)"
      />
    </div>
  </div>
</template>
