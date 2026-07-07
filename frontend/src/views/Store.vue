<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api } from '@/api/client'
import type { StoreApp } from '@/api/types'

const apps = ref<StoreApp[]>([])
const PAGE_SIZE = 24
const categories = ref<string[]>([])

const q = ref('')
const category = ref('')
const tag = ref('')
const mode = ref<'all' | 'available' | 'installed'>('all')
const page = ref(1)
const visibleApps = computed(() => {
  if (mode.value === 'available') return apps.value.filter((app) => !app.installed)
  if (mode.value === 'installed') return apps.value.filter((app) => app.installed)
  return apps.value
})
const pageCount = computed(() => Math.max(1, Math.ceil(visibleApps.value.length / PAGE_SIZE)))
const shownApps = computed(() => visibleApps.value.slice((page.value - 1) * PAGE_SIZE, page.value * PAGE_SIZE))
const topTags = computed(() => {
  const counts = new Map<string, number>()
  for (const app of apps.value) {
    for (const t of app.tags) counts.set(t, (counts.get(t) ?? 0) + 1)
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 18)
})

const loading = ref(false)
const syncing = ref(false)
const error = ref('')

const previews = ref<Record<string, string>>({})
const previewErrors = ref<Record<string, string>>({})
const previewing = ref<Record<string, boolean>>({})

const installErrors = ref<Record<string, string>>({})
const installing = ref<Record<string, boolean>>({})

async function loadCategories(): Promise<void> {
  try {
    categories.value = await api.storeCategories()
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'Failed to load categories'
  }
}

async function loadList(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    apps.value = await api.listStore(q.value, category.value, tag.value)
    page.value = 1
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'Failed to load catalog'
  } finally {
    loading.value = false
  }
}

function onSearch(): void {
  void loadList()
}

function onCategoryChange(): void {
  void loadList()
}

function setTag(next: string): void {
  tag.value = tag.value === next ? '' : next
  void loadList()
}

function setMode(next: 'all' | 'available' | 'installed'): void {
  mode.value = next
  page.value = 1
}

function nextPage(): void {
  page.value = Math.min(page.value + 1, pageCount.value)
}

function previousPage(): void {
  page.value = Math.max(page.value - 1, 1)
}

async function sync(): Promise<void> {
  syncing.value = true
  error.value = ''
  try {
    await api.syncStore()
    await loadList()
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'Failed to sync catalog'
  } finally {
    syncing.value = false
  }
}

async function preview(app: StoreApp): Promise<void> {
  previewing.value[app.name] = true
  previewErrors.value[app.name] = ''
  try {
    const res = await api.previewStore(app.name)
    if (res.error) {
      previewErrors.value[app.name] = res.error
    } else {
      // The store-preview endpoint renders to outputs/<safe_name>.large.webp but
      // returns {name, preview:true} (no url), so build it here. Backend maps
      // hyphens to underscores for the on-disk name.
      const safe = app.name.replace(/-/g, '_')
      previews.value[app.name] = res.preview_url ?? `/static/outputs/${encodeURIComponent(safe)}.large.webp?t=${Date.now()}`
    }
  } catch (e: unknown) {
    previewErrors.value[app.name] = e instanceof Error ? e.message : 'Preview failed'
  } finally {
    previewing.value[app.name] = false
  }
}

async function install(app: StoreApp): Promise<void> {
  installing.value[app.name] = true
  installErrors.value[app.name] = ''
  try {
    const res = await api.installStore(app.name)
    if ('error' in res) {
      installErrors.value[app.name] = res.error
    } else {
      app.installed = true
    }
  } catch (e: unknown) {
    installErrors.value[app.name] = e instanceof Error ? e.message : 'Install failed'
  } finally {
    installing.value[app.name] = false
  }
}

onMounted(() => {
  void loadCategories()
  void loadList()
})
</script>

<template>
  <div class="scanlines min-h-full">
    <div class="mx-auto max-w-5xl px-5 py-6">
      <header class="mb-5">
        <p class="text-[11px] uppercase tracking-[0.22em] text-ember mb-1">Community Store</p>
        <h2 class="text-xl font-bold text-core mb-5">Browse &amp; install pixel-art apps</h2>

        <!-- toolbar -->
        <form
          class="flex flex-wrap items-center gap-2"
          @submit.prevent="onSearch"
        >
          <input
            v-model="q"
            type="text"
            placeholder="search apps…"
            :disabled="loading || syncing"
            class="min-w-[10rem] flex-1 bg-[#120a10] border border-[#3a2016] text-gold px-2 py-1.5 text-xs rounded focus:outline-none focus:border-flame disabled:opacity-50"
          />
          <select
            v-model="category"
            :disabled="loading || syncing"
            class="bg-[#120a10] border border-[#3a2016] text-gold px-2 py-1.5 text-xs rounded focus:outline-none focus:border-flame disabled:opacity-50"
            @change="onCategoryChange"
          >
            <option value="">all categories</option>
            <option v-for="c in categories" :key="c" :value="c">{{ c }}</option>
          </select>
          <button
            type="submit"
            :disabled="loading || syncing"
            class="rounded border border-[#3a2016] px-2.5 py-1 text-[11px] uppercase tracking-wider text-gold hover:bg-[#251009] disabled:opacity-50"
          >
            Search
          </button>
          <button
            type="button"
            :disabled="loading || syncing"
            class="rounded border border-[#3a2016] px-2.5 py-1 text-[11px] uppercase tracking-wider text-gold hover:bg-[#251009] disabled:opacity-50"
            @click="sync"
          >
            {{ syncing ? 'syncing…' : 'Sync catalog' }}
          </button>
        </form>

        <div class="mt-3 flex flex-wrap items-center gap-1.5 font-mono text-[10px] uppercase tracking-wider">
          <button
            class="rounded border border-[#3a2016] px-2 py-1"
            :class="mode === 'all' ? 'bg-flame text-[#160a0a]' : 'text-dim hover:text-gold'"
            @click="setMode('all')"
          >
            All
          </button>
          <button
            class="rounded border border-[#3a2016] px-2 py-1"
            :class="mode === 'available' ? 'bg-flame text-[#160a0a]' : 'text-dim hover:text-gold'"
            @click="setMode('available')"
          >
            Available
          </button>
          <button
            class="rounded border border-[#3a2016] px-2 py-1"
            :class="mode === 'installed' ? 'bg-flame text-[#160a0a]' : 'text-dim hover:text-gold'"
            @click="setMode('installed')"
          >
            Installed
          </button>
        </div>

        <div v-if="topTags.length" class="mt-3 flex flex-wrap gap-1">
          <button
            v-for="[name, count] in topTags"
            :key="name"
            class="rounded border px-1.5 py-0.5 text-[10px]"
            :class="tag === name ? 'border-flame bg-flame text-[#160a0a]' : 'border-[#3a2016] text-[#c78a5a] hover:bg-[#251009] hover:text-gold'"
            @click="setTag(name)"
          >
            #{{ name }} {{ count }}
          </button>
        </div>

        <!-- status row -->
        <div class="mt-3 flex flex-wrap items-center gap-3 font-mono text-[11px] uppercase tracking-wider">
          <span v-if="loading" class="text-dim"><span class="blink">▮</span> Loading catalog…</span>
          <span v-else class="text-dim">
            {{ visibleApps.length }} app{{ visibleApps.length === 1 ? '' : 's' }}
            <span v-if="tag"> · #{{ tag }}</span>
            <span v-if="visibleApps.length"> · page {{ page }}/{{ pageCount }}</span>
          </span>
          <button v-if="tag" class="text-gold hover:text-core" @click="setTag('')">Clear tag</button>
        </div>
        <p v-if="error" class="mt-1 text-[11px] text-[#ff6a4a]">{{ error }}</p>
      </header>

      <!-- results -->
      <div v-if="visibleApps.length" class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <div
          v-for="app in shownApps"
          :key="app.name"
          class="border border-[#3a2016] rounded bg-panel p-3"
        >
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <h3 class="truncate font-mono text-sm text-gold">{{ app.name }}</h3>
              <p class="text-[11px] text-dim">by {{ app.author }}</p>
            </div>
            <span
              v-if="app.supports_2x"
              class="shrink-0 rounded border border-[#3a2016] px-1 py-0.5 text-[9px] font-bold uppercase tracking-wider text-flame"
            >
              2×
            </span>
          </div>

          <p class="mt-1.5 text-xs text-muted">{{ app.summary }}</p>

          <div v-if="app.tags.length" class="mt-2 flex flex-wrap gap-1">
            <button
              v-for="tag in app.tags"
              :key="tag"
              class="rounded bg-[#251009] px-1.5 py-0.5 text-[10px] text-[#c78a5a] hover:text-gold"
              @click="setTag(tag)"
            >
              #{{ tag }}
            </button>
          </div>

          <!-- preview bezel -->
          <div v-if="previews[app.name]" class="mt-2.5 flex justify-center">
            <div class="rounded-lg border-2 border-[#24121c] bg-black p-1.5">
              <img class="px w-24 h-24 object-contain" :src="previews[app.name]" :alt="app.name" />
            </div>
          </div>

          <p v-if="previewErrors[app.name]" class="mt-1.5 text-[11px] text-[#ff6a4a]">
            {{ previewErrors[app.name] }}
          </p>
          <p v-if="installErrors[app.name]" class="mt-1.5 text-[11px] text-[#ff6a4a]">
            {{ installErrors[app.name] }}
          </p>

          <!-- actions -->
          <div class="mt-3 flex items-center gap-2 border-t border-[#1c0e14] pt-2.5 font-mono text-[11px] uppercase tracking-wider">
            <button
              type="button"
              :disabled="previewing[app.name]"
              class="rounded border border-[#3a2016] px-2.5 py-1 text-gold hover:bg-[#251009] disabled:opacity-50"
              @click="preview(app)"
            >
              {{ previewing[app.name] ? '…' : 'Preview' }}
            </button>

            <button
              v-if="!app.installed"
              type="button"
              :disabled="installing[app.name]"
              class="ml-auto rounded bg-flame px-2.5 py-1 text-[#160a0a] disabled:opacity-50"
              @click="install(app)"
            >
              {{ installing[app.name] ? 'installing…' : 'Install' }}
            </button>
            <span v-else class="ml-auto px-2.5 py-1 text-[#7a4a34]">Installed</span>
          </div>
        </div>
      </div>

      <div v-if="visibleApps.length > PAGE_SIZE" class="mt-4 flex items-center justify-center gap-3 font-mono text-[11px] uppercase tracking-wider">
        <button
          class="rounded border border-[#3a2016] px-2.5 py-1 text-gold hover:bg-[#251009] disabled:opacity-40"
          :disabled="page <= 1"
          @click="previousPage"
        >
          Prev
        </button>
        <span class="text-dim">{{ page }} / {{ pageCount }}</span>
        <button
          class="rounded border border-[#3a2016] px-2.5 py-1 text-gold hover:bg-[#251009] disabled:opacity-40"
          :disabled="page >= pageCount"
          @click="nextPage"
        >
          Next
        </button>
      </div>

      <p v-if="!loading && !visibleApps.length" class="font-mono text-[11px] text-dim">
        No apps found. Try a different search or sync the catalog.
      </p>
    </div>
  </div>
</template>
