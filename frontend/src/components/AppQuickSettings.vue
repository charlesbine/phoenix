<script setup lang="ts">
import { computed, ref } from 'vue'
import { api } from '@/api/client'
import type { AppItem, SchemaField } from '@/api/types'
import AppSettingsFields from '@/components/AppSettingsFields.vue'

const props = defineProps<{ app: AppItem }>()
const emit = defineEmits<{ rendered: [] }>()
const canRenderPreview = computed(() => !props.app.is_live || props.app.app_type === 'live_matrix')
const schema = ref<SchemaField[] | null>(null)
const values = ref<Record<string, string>>({})
const saved = ref<Record<string, string>>({})
const loading = ref(false)
const saving = ref(false)
const note = ref('')
const error = ref('')

async function load(event: Event): Promise<void> {
  if (!(event.target as HTMLDetailsElement).open || schema.value || loading.value) return
  loading.value = true
  error.value = ''
  try {
    const fields = await api.getSchema(props.app.name)
    values.value = Object.fromEntries(fields.map((field) => [
      field.id, String(props.app.pixlet_config[field.id] ?? field.default ?? ''),
    ]))
    saved.value = { ...values.value }
    schema.value = fields
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

async function save(): Promise<void> {
  if (!schema.value?.length || saving.value) return
  saving.value = true
  note.value = ''
  error.value = ''
  const name = props.app.name
  const edits = Object.fromEntries(Object.entries(values.value).filter(([id, value]) => value !== saved.value[id]))
  try {
    if (Object.keys(edits).length) {
      await api.setAppConfig(name, { ...props.app.pixlet_config, ...edits })
      saved.value = { ...values.value }
    }
    if (!canRenderPreview.value) {
      note.value = 'Settings saved.'
      return
    }
    note.value = 'Rendering…'
    const result = await api.preview(name)
    if (result.error) {
      error.value = result.error
      return
    }
    note.value = result.info ?? 'Preview updated.'
    emit('rendered')
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    saving.value = false
    if (error.value) note.value = ''
  }
}
</script>

<template>
  <details class="mt-3 rounded border border-[#3a2016] bg-panel p-3" @toggle="load">
    <summary class="cursor-pointer text-xs text-gold focus-visible:outline-flame">Settings</summary>
    <p v-if="loading" class="mt-2 text-xs text-muted" role="status">Loading settings…</p>
    <p v-else-if="schema?.length === 0" class="mt-2 text-xs text-muted">This app has no configurable settings.</p>
    <form v-else-if="schema?.length" class="mt-3" @submit.prevent="save">
      <p class="mb-3 text-xs text-muted">Applies to all panels.</p>
      <fieldset :disabled="saving">
        <AppSettingsFields :schema="schema" :values="values" @change="(id, value) => values[id] = value" />
        <button class="mt-3 rounded bg-flame px-3 py-1.5 text-xs text-[#160a0a] disabled:opacity-60" type="submit">
          {{ canRenderPreview ? 'Save & render' : 'Save settings' }}
        </button>
      </fieldset>
    </form>
    <p v-if="note" class="mt-2 text-xs text-gold" role="status">{{ note }}</p>
    <p v-if="error" class="mt-2 text-xs text-[#ff6a4a]" role="alert">{{ error }}</p>
  </details>
</template>
