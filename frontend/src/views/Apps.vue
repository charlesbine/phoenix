<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { api } from '@/api/client'
import type { AppItem, SchemaField } from '@/api/types'
import MatrixPreview from '@/components/MatrixPreview.vue'

const apps = ref<AppItem[]>([])
const available = ref<string[]>([])
const selected = ref<string | null>(null)
const schema = ref<SchemaField[]>([])
const values = reactive<Record<string, string>>({})
const tick = ref(0)
const error = ref<string | null>(null)
const note = ref<string | null>(null)
const addPick = ref('')
const showDisabled = ref(false)
const visibleApps = computed(() =>
  showDisabled.value ? apps.value : apps.value.filter((a) => a.enabled),
)

const PRESETS = ['realtime', 'frequent', 'ambient']
const selectedApp = computed(() => apps.value.find((a) => a.name === selected.value) ?? null)

async function load(): Promise<void> {
  try {
    const list = await api.listApps()
    apps.value = list.sort((a, b) => a.sort_order - b.sort_order)
    available.value = await api.availableApps()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}
onMounted(load)

function replace(u: AppItem): void {
  const i = apps.value.findIndex((x) => x.name === u.name)
  if (i >= 0) apps.value[i] = u
}

async function selectApp(name: string): Promise<void> {
  selected.value = name
  note.value = null
  schema.value = []
  for (const k of Object.keys(values)) delete values[k]
  try {
    schema.value = await api.getSchema(name)
  } catch {
    schema.value = []
  }
  for (const f of schema.value) values[f.id] = f.default ?? ''
  const cfg = apps.value.find((a) => a.name === name)?.pixlet_config ?? {}
  for (const [k, v] of Object.entries(cfg)) values[k] = String(v)
  tick.value++
}

async function saveConfig(): Promise<void> {
  if (!selected.value) return
  try {
    replace(await api.setAppConfig(selected.value, { ...values }))
    note.value = 'saved · rendering…'
    const r = await api.preview(selected.value)
    note.value = r?.error ?? r?.info ?? 'saved'
    tick.value++
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}

async function renderPreview(): Promise<void> {
  if (!selected.value) return
  note.value = 'rendering…'
  const r = await api.preview(selected.value)
  note.value = r?.error ?? r?.info ?? null
  tick.value++
}

async function toggleEnabled(a: AppItem): Promise<void> {
  replace(a.enabled ? await api.disable(a.name) : await api.enable(a.name))
}
async function toggleActive(a: AppItem): Promise<void> {
  replace(a.active ? await api.deactivate(a.name) : await api.activate(a.name))
}
async function setPreset(name: string, preset: string): Promise<void> {
  replace(await api.setPreset(name, preset))
}
async function setPriority(name: string, priority: number): Promise<void> {
  replace(await api.setPriority(name, Math.max(0, priority)))
}
async function removeApp(name: string): Promise<void> {
  if (!confirm(`Delete "${name}"? This removes it from the rotation.`)) return
  await api.deleteApp(name)
  if (selected.value === name) selected.value = null
  await load()
}
async function addApp(): Promise<void> {
  if (!addPick.value) return
  const name = addPick.value
  addPick.value = ''
  try {
    await api.addApp(name)
    await load()
    await selectApp(name)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}

// --- drag reorder ---
const dragName = ref<string | null>(null)
function onDrop(target: string): void {
  const from = dragName.value
  dragName.value = null
  if (!from || from === target) return
  const order = apps.value.map((a) => a.name)
  const fi = order.indexOf(from)
  const ti = order.indexOf(target)
  order.splice(ti, 0, order.splice(fi, 1)[0])
  apps.value = order.map((n) => apps.value.find((a) => a.name === n)!)
  api.reorder(order).catch((e: unknown) => {
    error.value = e instanceof Error ? e.message : String(e)
  })
}

function onValue(id: string, e: Event): void {
  const t = e.target as HTMLInputElement
  values[id] = t.type === 'checkbox' ? (t.checked ? 'true' : 'false') : t.value
}
</script>

<template>
  <div>
    <p class="mb-1 text-[11px] uppercase tracking-[0.22em] text-ember">Apps</p>
    <h2 class="mb-5 text-xl font-bold text-core">Rotation &amp; configuration</h2>
    <p v-if="error" class="mb-3 text-[11px] text-[#ff6a4a]">{{ error }}</p>

    <div class="grid gap-5 md:grid-cols-2">
      <!-- rotation list (drag to reorder) -->
      <section>
        <div class="mb-2 flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.18em] text-dim">
          <span>Rotation · {{ apps.length }} · drag to reorder</span>
          <button class="hover:text-gold" :class="showDisabled ? 'text-gold' : ''" @click="showDisabled = !showDisabled">
            {{ showDisabled ? '− hide disabled' : '+ show disabled' }}
          </button>
        </div>
        <ul class="rounded border border-[#3a2016]">
          <li
            v-for="a in visibleApps"
            :key="a.name"
            draggable="true"
            class="flex cursor-grab items-center gap-2.5 border-b border-[#1c0e14] px-3 py-2 text-xs uppercase tracking-wide last:border-b-0"
            :class="a.name === selected ? 'bg-[#1e0f18]' : 'hover:bg-[#160b12]'"
            @dragstart="dragName = a.name"
            @dragover.prevent
            @drop="onDrop(a.name)"
          >
            <span class="shrink-0 text-dim">⠿</span>
            <button class="flex-1 truncate text-left" :class="a.name === selected ? 'text-core' : 'text-gold'" @click="selectApp(a.name)">
              {{ a.name }}
            </button>
            <span v-if="a.priority > 0" class="shrink-0 text-[10px] text-[#ff6a4a]">×{{ a.priority + 1 }}</span>
            <button class="w-8 shrink-0 text-right text-[10px]" :class="a.enabled ? 'text-flame' : 'text-[#7a4a34]'" @click="toggleEnabled(a)">
              {{ a.enabled ? 'ON' : 'OFF' }}
            </button>
          </li>
        </ul>

        <!-- add app -->
        <div class="mt-3 flex items-center gap-2">
          <select v-model="addPick" class="flex-1 rounded border border-[#3a2016] bg-[#120a10] px-2 py-1.5 text-xs text-gold focus:border-flame focus:outline-none">
            <option value="">Add an app…</option>
            <option v-for="n in available" :key="n" :value="n">{{ n }}</option>
          </select>
          <button class="rounded border border-[#3a2016] px-2.5 py-1.5 text-[11px] uppercase tracking-wider text-gold hover:bg-[#251009] disabled:opacity-40" :disabled="!addPick" @click="addApp">Add</button>
        </div>
      </section>

      <!-- detail / config editor -->
      <section v-if="selectedApp" class="flex flex-col gap-4">
        <MatrixPreview :app="selected" :tick="tick" @render="renderPreview" />
        <p v-if="note" class="font-mono text-[10px] text-[#c78a5a]">{{ note }}</p>

        <!-- settings -->
        <div class="flex flex-wrap items-center gap-2 font-mono text-[11px] uppercase tracking-wider">
          <button class="rounded border border-[#3a2016] px-2.5 py-1 text-gold hover:bg-[#251009]" @click="api.showNow(selectedApp.name)">▷ show</button>
          <button class="rounded px-2.5 py-1" :class="selectedApp.enabled ? 'text-flame' : 'text-[#7a4a34]'" @click="toggleEnabled(selectedApp)">{{ selectedApp.enabled ? 'enabled' : 'disabled' }}</button>
          <button class="rounded px-2.5 py-1" :class="selectedApp.active ? 'text-flame' : 'text-[#7a4a34]'" @click="toggleActive(selectedApp)">{{ selectedApp.active ? 'active' : 'inactive' }}</button>
          <button class="ml-auto rounded border border-[#3a2016] px-2.5 py-1 text-[#ff6a4a] hover:bg-[#251009]" @click="removeApp(selectedApp.name)">delete</button>
        </div>

        <!-- refresh preset + priority -->
        <div class="flex flex-wrap items-center gap-3 font-mono text-[11px] uppercase tracking-wider">
          <div class="flex items-center gap-1">
            <span class="text-dim">refresh</span>
            <button
              v-for="p in PRESETS"
              :key="p"
              class="rounded border border-[#3a2016] px-2 py-1"
              :class="selectedApp.refresh_preset === p ? 'bg-flame text-[#160a0a]' : 'text-dim hover:text-gold'"
              @click="setPreset(selectedApp.name, p)"
            >
              {{ p }}
            </button>
          </div>
          <div class="flex items-center gap-1.5 text-dim">
            <span>weight</span>
            <button class="px-1 text-gold hover:text-core" @click="setPriority(selectedApp.name, selectedApp.priority - 1)">−</button>
            <span class="text-gold">×{{ selectedApp.priority + 1 }}</span>
            <button class="px-1 text-gold hover:text-core" @click="setPriority(selectedApp.name, selectedApp.priority + 1)">+</button>
          </div>
        </div>

        <!-- schema-driven config -->
        <div v-if="schema.length" class="rounded border border-[#3a2016] bg-panel p-3">
          <div class="mb-3 text-[10px] uppercase tracking-[0.18em] text-dim">Settings</div>
          <div class="flex flex-col gap-3">
            <div v-for="f in schema" :key="f.id">
              <label class="mb-1 block text-[10px] uppercase tracking-[0.14em] text-dim">{{ f.name ?? f.id }}</label>
              <p v-if="f.desc" class="mb-1 text-[10px] normal-case text-muted">{{ f.desc }}</p>

              <select v-if="f.type === 'dropdown'" :value="values[f.id]" class="w-full rounded border border-[#3a2016] bg-[#120a10] px-2 py-1.5 text-xs text-gold focus:border-flame focus:outline-none" @change="onValue(f.id, $event)">
                <option v-for="o in f.options ?? []" :key="o.value" :value="o.value">{{ o.display }}</option>
              </select>

              <label v-else-if="f.type === 'toggle'" class="flex items-center gap-2 text-xs text-gold">
                <input type="checkbox" :checked="values[f.id] === 'true'" @change="onValue(f.id, $event)" />
                {{ values[f.id] === 'true' ? 'on' : 'off' }}
              </label>

              <input v-else-if="f.type === 'color'" type="color" :value="values[f.id] || '#000000'" class="h-8 w-16 rounded border border-[#3a2016] bg-[#120a10]" @input="onValue(f.id, $event)" />

              <input v-else :value="values[f.id]" type="text" class="w-full rounded border border-[#3a2016] bg-[#120a10] px-2 py-1.5 text-xs text-gold focus:border-flame focus:outline-none" @input="onValue(f.id, $event)" />
            </div>
          </div>
          <button class="mt-4 rounded bg-flame px-3 py-1.5 text-[11px] uppercase tracking-wider text-[#160a0a]" @click="saveConfig">Save settings</button>
        </div>
        <p v-else class="text-[11px] text-dim">This app has no configurable settings.</p>
      </section>

      <section v-else class="grid place-items-center rounded border border-dashed border-[#3a2016] p-10 text-[11px] uppercase tracking-widest text-dim">
        Select an app to configure
      </section>
    </div>
  </div>
</template>
