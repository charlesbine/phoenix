<script setup lang="ts">
import { api } from '@/api/client'
import type { Playlist, ScheduleRule, Schedule, AppItem } from '@/api/types'
import { ref, reactive, computed, onMounted } from 'vue'

const DAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'] as const

// --- state ---
const apps = ref<AppItem[]>([])
const playlists = ref<Playlist[]>([])
const schedule = ref<Schedule | null>(null)

const playlistError = ref('')
const scheduleError = ref('')

const newPlaylist = reactive<{ id: string; name: string; app_names: string[] }>({
  id: '',
  name: '',
  app_names: [],
})
const newRule = reactive<{ playlist_id: string; start_time: string; end_time: string; days: string[] }>({
  playlist_id: '',
  start_time: '09:00',
  end_time: '17:00',
  days: [...DAYS],
})

const playlistApps = computed<AppItem[]>(() => apps.value.filter((app) => app.active))

const activePlaylistLabel = computed<string>(() => {
  const active = schedule.value?.active_playlist
  if (!active) return 'none'
  const match = playlists.value.find((p: Playlist): boolean => p.id === active)
  return match ? match.name : active
})

// --- helpers ---
function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}

function orderedDays(days: string[]): string[] {
  return DAYS.filter((d: string): boolean => days.includes(d))
}

function slugify(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
}

// --- loaders ---
async function loadApps(): Promise<void> {
  try {
    apps.value = await api.listApps()
  } catch (e: unknown) {
    playlistError.value = errMsg(e)
  }
}

async function loadPlaylists(): Promise<void> {
  try {
    playlists.value = await api.listPlaylists()
  } catch (e: unknown) {
    playlistError.value = errMsg(e)
  }
}

async function loadSchedule(): Promise<void> {
  try {
    schedule.value = await api.getSchedule()
  } catch (e: unknown) {
    scheduleError.value = errMsg(e)
  }
}

// --- playlist actions ---
async function toggleMember(pl: Playlist, appName: string): Promise<void> {
  playlistError.value = ''
  const inList = pl.app_names.includes(appName)
  const app_names = inList
    ? pl.app_names.filter((n: string): boolean => n !== appName)
    : [...pl.app_names, appName]
  try {
    const updated = await api.updatePlaylist(pl.id, { app_names })
    const idx = playlists.value.findIndex((p: Playlist): boolean => p.id === pl.id)
    if (idx !== -1) playlists.value[idx] = updated
  } catch (e: unknown) {
    playlistError.value = errMsg(e)
  }
}

async function removePlaylist(pl: Playlist): Promise<void> {
  if (!window.confirm(`Delete playlist "${pl.name}"?`)) return
  playlistError.value = ''
  try {
    await api.deletePlaylist(pl.id)
    await loadPlaylists()
    await loadSchedule()
  } catch (e: unknown) {
    playlistError.value = errMsg(e)
  }
}

async function createPlaylist(): Promise<void> {
  playlistError.value = ''
  const id = slugify(newPlaylist.id || newPlaylist.name)
  const name = newPlaylist.name.trim()
  if (!id || !name) {
    playlistError.value = 'Name is required'
    return
  }
  try {
    const result = await api.createPlaylist({ id, name, app_names: [...newPlaylist.app_names] })
    if ('error' in result) {
      playlistError.value = result.error
      return
    }
    newPlaylist.id = ''
    newPlaylist.name = ''
    newPlaylist.app_names = []
    await loadPlaylists()
    await loadSchedule()
  } catch (e: unknown) {
    playlistError.value = errMsg(e)
  }
}

// --- schedule actions ---
function toggleRuleDay(day: string): void {
  const idx = newRule.days.indexOf(day)
  if (idx === -1) newRule.days.push(day)
  else newRule.days.splice(idx, 1)
}

function toggleNewPlaylistMember(appName: string): void {
  const idx = newPlaylist.app_names.indexOf(appName)
  if (idx === -1) newPlaylist.app_names.push(appName)
  else newPlaylist.app_names.splice(idx, 1)
}

async function addRule(): Promise<void> {
  scheduleError.value = ''
  if (!newRule.playlist_id) {
    scheduleError.value = 'Select a playlist'
    return
  }
  if (!newRule.start_time || !newRule.end_time) {
    scheduleError.value = 'Start and end time are required'
    return
  }
  if (!newRule.days.length) {
    scheduleError.value = 'Select at least one day'
    return
  }
  try {
    await api.createRule({
      playlist_id: newRule.playlist_id,
      start_time: newRule.start_time,
      end_time: newRule.end_time,
      days: [...newRule.days],
    })
    newRule.playlist_id = ''
    newRule.start_time = '09:00'
    newRule.end_time = '17:00'
    newRule.days = [...DAYS]
    await loadSchedule()
  } catch (e: unknown) {
    scheduleError.value = errMsg(e)
  }
}

async function removeRule(rule: ScheduleRule): Promise<void> {
  scheduleError.value = ''
  try {
    await api.deleteRule(rule.id)
    await loadSchedule()
  } catch (e: unknown) {
    scheduleError.value = errMsg(e)
  }
}

onMounted(() => {
  void loadApps()
  void loadPlaylists()
  void loadSchedule()
})
</script>

<template>
  <div class="scanlines min-h-full font-mono">
    <div class="mx-auto max-w-5xl px-5 py-6">
      <!-- header -->
      <header class="mb-6">
        <p class="text-[11px] uppercase tracking-[0.22em] text-ember mb-1">Playlists &amp; Schedule</p>
        <h2 class="text-xl font-bold text-core mb-5">Curate rotations &amp; set when they burn</h2>
      </header>

      <!-- ============================ PLAYLISTS ============================ -->
      <section class="mb-10">
        <div class="mb-3 flex items-center justify-between">
          <h3 class="text-[10px] uppercase tracking-[0.18em] text-dim">Playlists</h3>
          <span class="text-[10px] uppercase tracking-[0.18em] text-muted">{{ playlists.length }} total</span>
        </div>

        <p v-if="playlistError" class="mb-3 text-[11px] text-[#ff6a4a]">{{ playlistError }}</p>

        <!-- playlist cards -->
        <div class="grid gap-3">
          <div
            v-for="pl in playlists"
            :key="pl.id"
            class="border border-[#3a2016] rounded bg-panel p-3"
          >
            <div class="flex items-start justify-between gap-3">
              <div>
                <p class="text-sm text-gold">{{ pl.name }}</p>
                <p class="text-[10px] uppercase tracking-[0.18em] text-dim mt-0.5">{{ pl.id }}</p>
              </div>
              <button
                class="rounded border border-[#3a2016] px-2.5 py-1 text-[11px] uppercase tracking-wider text-[#ff6a4a] hover:bg-[#251009]"
                @click="removePlaylist(pl)"
              >
                Delete
              </button>
            </div>

            <!-- current members -->
            <div class="mt-3">
              <p class="text-[10px] uppercase tracking-[0.18em] text-muted mb-1.5">
                Members · {{ pl.app_names.length }}
              </p>
              <div v-if="pl.app_names.length" class="flex flex-wrap gap-1.5">
                <button
                  v-for="name in pl.app_names"
                  :key="name"
                  class="rounded px-2 py-0.5 text-[11px] uppercase tracking-wider bg-flame text-[#160a0a]"
                  title="Click to remove"
                  @click="toggleMember(pl, name)"
                >
                  {{ name }}
                </button>
              </div>
              <p v-else class="text-[11px] text-dim">No apps in this playlist yet.</p>
            </div>

            <!-- add / toggle from all apps -->
            <div class="mt-3 border-t border-[#1c0e14] pt-3">
              <p class="text-[10px] uppercase tracking-[0.18em] text-muted mb-1.5">Add apps</p>
              <div v-if="playlistApps.length" class="flex flex-wrap gap-1.5">
                <button
                  v-for="app in playlistApps"
                  :key="app.name"
                  class="rounded px-2 py-0.5 text-[11px] uppercase tracking-wider"
                  :class="
                    pl.app_names.includes(app.name)
                      ? 'bg-flame text-[#160a0a]'
                      : 'border border-[#3a2016] text-dim hover:bg-[#251009]'
                  "
                  @click="toggleMember(pl, app.name)"
                >
                  {{ app.name }}
                </button>
              </div>
              <p v-else class="text-[11px] text-dim">No apps available.</p>
            </div>
          </div>

          <p v-if="!playlists.length" class="text-[11px] text-dim">No playlists yet. Create one below.</p>
        </div>

        <!-- new playlist form -->
        <div class="mt-4 border border-[#3a2016] rounded bg-panel p-3">
          <p class="text-[10px] uppercase tracking-[0.18em] text-muted mb-2">New playlist</p>
          <form class="flex flex-col gap-3" @submit.prevent="createPlaylist">
            <div class="flex flex-wrap items-center gap-2">
              <input
                v-model="newPlaylist.name"
                type="text"
                placeholder="Playlist name"
                class="bg-[#120a10] border border-[#3a2016] text-gold px-2 py-1.5 text-xs rounded focus:outline-none focus:border-flame"
              />
              <input
                v-model="newPlaylist.id"
                type="text"
                :placeholder="slugify(newPlaylist.name) || 'id'"
                class="bg-[#120a10] border border-[#3a2016] text-gold px-2 py-1.5 text-xs rounded focus:outline-none focus:border-flame"
              />
              <button
                type="submit"
                class="rounded border border-[#3a2016] px-2.5 py-1 text-[11px] uppercase tracking-wider bg-flame text-[#160a0a]"
              >
                Create
              </button>
            </div>

            <div v-if="playlistApps.length" class="flex flex-wrap gap-1.5">
              <button
                v-for="app in playlistApps"
                :key="app.name"
                type="button"
                class="rounded px-2 py-0.5 text-[11px] uppercase tracking-wider"
                :class="
                  newPlaylist.app_names.includes(app.name)
                    ? 'bg-flame text-[#160a0a]'
                    : 'border border-[#3a2016] text-dim hover:bg-[#251009]'
                "
                @click="toggleNewPlaylistMember(app.name)"
              >
                {{ app.name }}
              </button>
            </div>
          </form>
        </div>
      </section>

      <!-- ============================ SCHEDULE ============================ -->
      <section>
        <div class="mb-3 flex items-center justify-between">
          <h3 class="text-[10px] uppercase tracking-[0.18em] text-dim">Schedule</h3>
          <span class="text-[10px] uppercase tracking-[0.18em] text-muted">
            active · <span class="text-gold">{{ activePlaylistLabel }}</span>
          </span>
        </div>

        <p v-if="scheduleError" class="mb-3 text-[11px] text-[#ff6a4a]">{{ scheduleError }}</p>

        <!-- rules -->
        <div class="grid gap-3">
          <div
            v-for="rule in schedule?.rules ?? []"
            :key="rule.id"
            class="border border-[#3a2016] rounded bg-panel p-3 flex items-start justify-between gap-3"
          >
            <div class="min-w-0">
              <p class="text-sm text-gold">{{ rule.playlist_name ?? rule.playlist_id }}</p>
              <p class="text-[11px] text-flame mt-0.5 tabular-nums">
                {{ rule.start_time }} – {{ rule.end_time }}
              </p>
              <div class="mt-2 flex flex-wrap gap-1">
                <span
                  v-for="d in orderedDays(rule.days)"
                  :key="d"
                  class="rounded border border-[#3a2016] px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-dim"
                >
                  {{ d }}
                </span>
              </div>
            </div>
            <button
              class="rounded border border-[#3a2016] px-2.5 py-1 text-[11px] uppercase tracking-wider text-[#ff6a4a] hover:bg-[#251009] shrink-0"
              @click="removeRule(rule)"
            >
              Delete
            </button>
          </div>

          <p v-if="!(schedule?.rules.length)" class="text-[11px] text-dim">No schedule rules yet.</p>
        </div>

        <!-- new rule form -->
        <div class="mt-4 border border-[#3a2016] rounded bg-panel p-3">
          <p class="text-[10px] uppercase tracking-[0.18em] text-muted mb-2">New rule</p>
          <form class="flex flex-col gap-3" @submit.prevent="addRule">
            <div class="flex flex-wrap items-center gap-2">
              <select
                v-model="newRule.playlist_id"
                class="bg-[#120a10] border border-[#3a2016] text-gold px-2 py-1.5 text-xs rounded focus:outline-none focus:border-flame"
              >
                <option value="" disabled>playlist…</option>
                <option v-for="pl in playlists" :key="pl.id" :value="pl.id">{{ pl.name }}</option>
              </select>
              <input
                v-model="newRule.start_time"
                type="time"
                class="bg-[#120a10] border border-[#3a2016] text-gold px-2 py-1.5 text-xs rounded focus:outline-none focus:border-flame"
              />
              <span class="text-dim text-xs">to</span>
              <input
                v-model="newRule.end_time"
                type="time"
                class="bg-[#120a10] border border-[#3a2016] text-gold px-2 py-1.5 text-xs rounded focus:outline-none focus:border-flame"
              />
            </div>

            <div class="flex flex-wrap gap-1.5">
              <button
                v-for="d in DAYS"
                :key="d"
                type="button"
                class="rounded px-2 py-0.5 text-[11px] uppercase tracking-wider"
                :class="
                  newRule.days.includes(d)
                    ? 'bg-flame text-[#160a0a]'
                    : 'border border-[#3a2016] text-dim hover:bg-[#251009]'
                "
                @click="toggleRuleDay(d)"
              >
                {{ d }}
              </button>
            </div>

            <div>
              <button
                type="submit"
                class="rounded border border-[#3a2016] px-2.5 py-1 text-[11px] uppercase tracking-wider bg-flame text-[#160a0a]"
              >
                Add rule
              </button>
            </div>
          </form>
        </div>
      </section>
    </div>
  </div>
</template>
