<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useMatrixStore } from '@/stores/matrix'
import { api } from '@/api/client'
import type { Config, Health } from '@/api/types'
import { formatUnhealthySummary, groupUnhealthyApps, type UnhealthyGroup } from '@/utils/health'
import MatrixPreview from '@/components/MatrixPreview.vue'
import BrightnessSlider from '@/components/BrightnessSlider.vue'
import AppRow from '@/components/AppRow.vue'
import AppQuickSettings from '@/components/AppQuickSettings.vue'

const store = useMatrixStore()
const { rotation, config, nowPlaying, nowPlayingLive, nodeSync, online, tick, note, previewApp, selectedApp, following } =
  storeToRefs(store)

const showDisabled = ref(false)
const singleAppSaving = ref(false)
const singleAppError = ref<string | null>(null)
const health = ref<Health | null>(null)
const healthError = ref<string | null>(null)
let healthTimer: number | null = null
const layoutModes: Config['layout_mode'][] = ['cycle', 'random', 'single']
const scheduleLabels = {
  daytime: 'Night Mode enabled',
  dimmed: 'Night Mode dimming',
  off: 'Night Mode · panel off',
  custom: 'Custom schedule',
}
const visibleRotation = computed(() =>
  showDisabled.value ? rotation.value : rotation.value.filter((a) => a.enabled),
)
const enabledRotationCount = computed(() => rotation.value.filter((a) => a.enabled).length)
const skippedRotationCount = computed(() =>
  rotation.value.filter((a) => a.enabled && a.skipped_unhealthy).length,
)
const downInCycleCount = computed(() =>
  rotation.value.filter((a) => a.enabled && a.health_status === 'unhealthy' && !a.skipped_unhealthy).length,
)
const cyclingRotationCount = computed(() => enabledRotationCount.value - skippedRotationCount.value)
const singleAppOptions = computed(() => rotation.value.filter((app) => app.enabled && app.active))
const singleAppValue = computed(() =>
  singleAppOptions.value.some((app) => app.name === config.value?.single_app) ? config.value?.single_app : '',
)
const previewLive = computed(() => selectedApp.value?.is_live ?? (following.value && nowPlayingLive.value))
const healthStatus = computed(() => health.value?.status ?? (healthError.value ? 'offline' : 'checking'))
const healthIssues = computed(() => health.value?.issues ?? (healthError.value ? [healthError.value] : []))
const unhealthyApps = computed(() => health.value?.unhealthy_apps ?? [])
const unhealthyGroups = computed(() => groupUnhealthyApps(unhealthyApps.value))
const unhealthySummary = computed(() => formatUnhealthySummary(unhealthyApps.value))
const hasActiveUnhealthy = computed(() => unhealthyApps.value.some((a) => !a.skipped_unhealthy))
const expandedGroups = ref<Record<string, boolean>>({})
const defaultExpandGroups = computed(() => unhealthyApps.value.length <= 3)
const hasExpandableGroups = computed(() => unhealthyGroups.value.some((g) => g.apps.length > 1))
const allGroupsExpanded = computed(() =>
  unhealthyGroups.value
    .filter((g) => g.apps.length > 1)
    .every((g) => isGroupExpanded(g)),
)
const m4Connected = computed(() => Boolean(health.value?.m4?.connected))
const mqttConnected = computed(() => Boolean(health.value?.mqtt?.connected))
const load1m = computed(() => health.value?.load?.['1m'])
const memoryUsed = computed(() => health.value?.memory?.used_pct)

function isGroupExpanded(group: UnhealthyGroup): boolean {
  if (group.apps.length <= 1) return false
  return expandedGroups.value[group.key] ?? defaultExpandGroups.value
}

function toggleGroup(key: string): void {
  const current = expandedGroups.value[key] ?? defaultExpandGroups.value
  expandedGroups.value = { ...expandedGroups.value, [key]: !current }
}

function toggleAllGroups(): void {
  const nextState = !allGroupsExpanded.value
  const updated: Record<string, boolean> = {}
  for (const g of unhealthyGroups.value) {
    if (g.apps.length > 1) updated[g.key] = nextState
  }
  expandedGroups.value = updated
}

function inspectApp(name: string): void {
  if (store.selected !== name) store.select(name)
}

async function toggleSkipWhenUnhealthy(): Promise<void> {
  if (!selectedApp.value) return
  await store.setSkipWhenUnhealthy(selectedApp.value.name, !selectedApp.value.skip_when_unhealthy)
  void refreshHealth()
}

async function refreshHealth(): Promise<void> {
  try {
    health.value = await api.health()
    healthError.value = null
  } catch (e) {
    healthError.value = e instanceof Error ? e.message : String(e)
  }
}

async function changeSingleApp(event: Event): Promise<void> {
  const select = event.target as HTMLSelectElement
  singleAppSaving.value = true
  singleAppError.value = null
  try {
    await store.setSingleApp(select.value || null)
  } catch (error) {
    select.value = singleAppValue.value ?? ''
    singleAppError.value = error instanceof Error ? error.message : String(error)
  } finally {
    singleAppSaving.value = false
  }
}

onMounted(() => {
  void store.refresh()
  store.connect()
  void refreshHealth()
  healthTimer = window.setInterval(() => void refreshHealth(), 60_000)
})
onUnmounted(() => {
  store.disconnect()
  if (healthTimer !== null) window.clearInterval(healthTimer)
})

</script>

<template>
  <div>
    <div class="grid gap-5 md:grid-cols-2">
      <!-- stage -->
      <section>
        <MatrixPreview
          :app="previewApp"
          :tick="tick"
          :device="store.activeDevice"
          :live="previewLive"
          @render="previewApp && store.render(previewApp)"
        />

        <div class="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] uppercase tracking-wider">
          <span class="text-dim">Preview <b class="text-gold">{{ previewApp ?? '—' }}</b></span>
          <span class="flex items-center gap-1.5 text-dim">
            <span class="h-2 w-2 rounded-full" :class="online ? 'bg-flame blink' : 'bg-[#7a4a34]'" style="box-shadow: 0 0 9px #ff6a2a"></span>
            live <b class="text-gold">{{ nowPlaying ?? '—' }}</b>
          </span>
          <span v-if="nodeSync" class="text-muted" role="status">
            {{ nodeSync === 'synced' ? 'Player synced' : nodeSync === 'pending' ? 'Player update pending' : 'Player offline · sync on reconnect' }}
          </span>
          <button v-if="!following" class="text-flame hover:text-gold" @click="store.followLive()">◉ follow live</button>
        </div>

        <p v-if="note" class="mt-1 font-mono text-[10px] text-[#c78a5a]">{{ note }}</p>

        <div v-if="selectedApp" class="mt-3 flex flex-wrap items-center gap-2 font-mono text-[11px] uppercase tracking-wider">
          <button class="rounded border border-[#3a2016] px-2.5 py-1 text-gold hover:bg-[#251009]" @click="store.showNow(selectedApp.name)">▷ show on display</button>
          <button class="rounded border border-[#3a2016] px-2.5 py-1 text-dim hover:bg-[#251009] hover:text-gold" @click="store.render(selectedApp.name)">⟳ render</button>
          <div class="flex items-center gap-1.5 text-dim">
            <span>weight</span>
            <button class="px-1 text-gold hover:text-core" @click="store.setPriority(selectedApp.name, selectedApp.priority - 1)">−</button>
            <span class="text-gold">×{{ selectedApp.priority + 1 }}</span>
            <button class="px-1 text-gold hover:text-core" @click="store.setPriority(selectedApp.name, selectedApp.priority + 1)">+</button>
          </div>
          <button
            class="rounded border px-2 py-1 text-[10px]"
            :class="selectedApp.skip_when_unhealthy
              ? 'border-flame/70 bg-[#251009] text-flame'
              : 'border-[#3a2016] text-dim hover:text-gold'"
            title="Skip this app in panel rotation while its data ingress is unhealthy"
            @click="toggleSkipWhenUnhealthy"
          >
            skip if down: {{ selectedApp.skip_when_unhealthy ? 'on' : 'off' }}
          </button>
          <button class="ml-auto rounded px-2.5 py-1" :class="selectedApp.enabled ? 'text-flame' : 'text-[#7a4a34]'" @click="store.toggle(selectedApp)">
            {{ selectedApp.enabled ? 'enabled' : 'disabled' }}
          </button>
        </div>

        <div
          v-if="selectedApp && selectedApp.health_status === 'unhealthy'"
          role="status"
          class="mt-3 rounded border border-[#b3241a] bg-[#1e0a0e] p-3 font-mono text-xs"
        >
          <div class="flex flex-wrap items-center justify-between gap-2 text-[10px] uppercase tracking-[0.16em]">
            <span class="text-[#ff6a4a]">▲ Data ingress unhealthy</span>
            <span
              v-if="selectedApp.skipped_unhealthy"
              class="rounded border border-[#b3241a] bg-[#2a0a0e] px-1.5 py-0.5 text-[9px] text-[#ff6a4a]"
            >
              skipped in cycle
            </span>
          </div>
          <p class="mt-1.5 text-[11px] text-core">
            {{ selectedApp.health_reason || 'Data source unavailable or empty.' }}
          </p>
          <p
            class="mt-1 text-[10px] uppercase tracking-[0.14em] text-muted"
            :title="selectedApp.last_healthy ?? undefined"
          >
            Last healthy: {{ selectedApp.last_healthy_human || 'never' }}
          </p>
        </div>
        <AppQuickSettings
          v-if="selectedApp && !following"
          :key="`${store.activeDevice}:${selectedApp.name}`"
          :app="selectedApp"
          @rendered="tick++"
        />
      </section>

      <!-- rotation -->
      <section class="flex flex-col gap-4">
        <div class="rounded border border-[#3a2016] bg-panel p-3">
          <div class="mb-3 flex items-center justify-between gap-3 font-mono text-[10px] uppercase tracking-[0.18em] text-dim">
            <span class="flex items-center gap-1.5">
              <span>System</span>
              <span>·</span>
              <span
                :class="
                  healthStatus === 'ok'
                    ? 'text-flame'
                    : healthStatus === 'degraded'
                      ? 'text-[#f0a552]'
                      : healthStatus === 'offline'
                        ? 'text-[#ff6a4a]'
                        : 'text-dim'
                "
              >
                {{ healthStatus }}
              </span>
            </span>
            <button class="text-gold hover:text-core" @click="refreshHealth">Refresh</button>
          </div>

          <div class="grid gap-2 font-mono text-[10px] uppercase tracking-[0.16em]"
            :class="health?.player || health?.m4 ? 'grid-cols-3' : 'grid-cols-2'">
            <div v-if="health?.player" class="min-w-0 rounded border border-[#24121c] px-2 py-1.5">
              <div class="flex items-center gap-1.5 text-dim">
                <span class="h-2 w-2 rounded-full" :class="health.player.status === 'synced' ? 'bg-flame' : 'bg-[#7a4a34]'"></span>
                Player
              </div>
              <div class="mt-1 truncate text-gold" :title="`${health.player.name} · ${health.player.status}`">
                {{ health.player.name }} · {{ health.player.status }}
              </div>
            </div>
            <div v-else-if="health?.m4" class="rounded border border-[#24121c] px-2 py-1.5">
              <div class="flex items-center gap-1.5 text-dim">
                <span class="h-2 w-2 rounded-full" :class="m4Connected ? 'bg-flame' : 'bg-[#7a4a34]'"></span>
                M4
              </div>
              <div class="mt-1 truncate text-gold">{{ health.m4.port ?? '—' }}</div>
            </div>
            <div class="rounded border border-[#24121c] px-2 py-1.5">
              <div class="flex items-center gap-1.5 text-dim">
                <span class="h-2 w-2 rounded-full" :class="mqttConnected ? 'bg-flame' : 'bg-[#7a4a34]'"></span>
                MQTT
              </div>
              <div class="mt-1 truncate text-gold">{{ health?.mqtt?.broker ?? '—' }}</div>
            </div>
            <div class="rounded border border-[#24121c] px-2 py-1.5">
              <div class="text-dim">Load</div>
              <div class="mt-1 truncate text-gold">
                {{ load1m ?? '—' }}<span v-if="memoryUsed !== undefined" class="text-dim"> · {{ memoryUsed }}%</span>
              </div>
            </div>
          </div>

          <div
            v-if="healthIssues.length"
            class="mt-3 space-y-1 border-t border-[#24121c] pt-2.5 font-mono text-[11px] text-[#e6a45c]"
          >
            <div v-for="issue in healthIssues" :key="issue" class="flex items-center gap-2">
              <span class="h-1.5 w-1.5 shrink-0 rounded-full bg-[#ff6a4a]"></span>
              <span class="truncate" :title="issue">{{ issue }}</span>
            </div>
          </div>

          <div v-if="unhealthyApps.length" class="mt-3 border-t border-[#24121c] pt-2.5">
            <div class="flex items-center justify-between gap-2">
              <div class="flex min-w-0 items-center gap-2 font-mono text-[10px]">
                <span
                  class="h-1.5 w-1.5 shrink-0 rounded-full"
                  :class="hasActiveUnhealthy ? 'bg-[#ff5a2a]' : 'bg-[#d98a3c]'"
                  :style="hasActiveUnhealthy ? 'box-shadow: 0 0 6px #ff5a2a' : ''"
                ></span>
                <span class="uppercase tracking-[0.16em] text-dim">Data ingress</span>
                <span class="truncate text-[#e6a45c]">{{ unhealthySummary }}</span>
              </div>
              <button
                v-if="hasExpandableGroups"
                class="shrink-0 font-mono text-[10px] text-dim hover:text-gold"
                @click="toggleAllGroups"
              >
                {{ allGroupsExpanded ? 'Collapse ▾' : 'Expand ▸' }}
              </button>
            </div>

            <div class="mt-2 divide-y divide-[#221118] rounded border border-[#3a1a1c] bg-[#12080d]/90">
              <div v-for="group in unhealthyGroups" :key="group.key">
                <!-- Single-app group: direct clickable row -->
                <button
                  v-if="group.apps.length === 1"
                  type="button"
                  class="flex w-full items-center gap-2 px-2.5 py-1.5 text-left font-mono text-[11px] transition-colors hover:bg-[#1c0c13]"
                  :class="previewApp === group.apps[0].app.name ? 'bg-[#1e0f18]' : ''"
                  :title="`${group.apps[0].app.reason || group.title} · Last healthy: ${group.apps[0].app.last_healthy_human || 'never'}`"
                  @click="inspectApp(group.apps[0].app.name)"
                >
                  <span
                    class="shrink-0"
                    :class="previewApp === group.apps[0].app.name ? 'text-core' : 'text-gold'"
                  >
                    {{ group.apps[0].app.name }}
                  </span>
                  <span class="min-w-0 flex-1 truncate text-[10px] text-muted">
                    {{ group.title }}
                  </span>
                  <span
                    class="shrink-0 rounded border px-1.5 py-0.5 text-[9px] tracking-wide"
                    :class="
                      group.apps[0].app.skipped_unhealthy
                        ? 'border-[#6b3c1e] bg-[#21120a] text-[#e6a45c]'
                        : 'border-[#8f241c] bg-[#260b0f] text-[#ff7b5c]'
                    "
                  >
                    {{ group.apps[0].app.skipped_unhealthy ? 'skipped' : 'in cycle' }}
                  </span>
                </button>

                <!-- Multi-app group: collapsible summary row + clickable app list -->
                <template v-else>
                  <button
                    type="button"
                    class="flex w-full items-center gap-2 px-2.5 py-1.5 text-left font-mono text-[11px] transition-colors hover:bg-[#1c0c13]"
                    :title="`${group.title} (${group.inlineNames})`"
                    @click="toggleGroup(group.key)"
                  >
                    <span class="w-2.5 shrink-0 text-[9px] text-dim">
                      {{ isGroupExpanded(group) ? '▾' : '▸' }}
                    </span>
                    <span class="min-w-0 flex-1 truncate text-core/90">{{ group.title }}</span>
                    <span
                      class="max-w-[9rem] shrink-0 truncate text-[10px] text-muted"
                      :title="group.inlineNames"
                    >
                      {{ group.apps.length <= 2 ? group.inlineNames : group.countLabel }}
                    </span>
                    <span
                      class="shrink-0 rounded border px-1.5 py-0.5 text-[9px] tracking-wide"
                      :class="
                        group.statusKind === 'skipped'
                          ? 'border-[#6b3c1e] bg-[#21120a] text-[#e6a45c]'
                          : group.statusKind === 'active'
                            ? 'border-[#8f241c] bg-[#260b0f] text-[#ff7b5c]'
                            : 'border-[#6b3c1e] bg-[#21120a] text-[#ff9e6a]'
                      "
                    >
                      {{
                        group.statusKind === 'skipped'
                          ? 'skipped'
                          : group.statusKind === 'active'
                            ? 'in cycle'
                            : `${group.skippedCount}/${group.apps.length} skip`
                      }}
                    </span>
                  </button>

                  <div
                    v-if="isGroupExpanded(group)"
                    class="border-t border-[#1e0f15] bg-[#0e060a]/80 py-1 pl-6 pr-2.5"
                  >
                    <button
                      v-for="entry in group.apps"
                      :key="entry.app.name"
                      type="button"
                      class="flex w-full items-center gap-2 rounded px-1.5 py-1 text-left font-mono text-[10px] transition-colors hover:bg-[#1c0c13]"
                      :class="previewApp === entry.app.name ? 'bg-[#1e0f18]' : ''"
                      :title="`${entry.app.reason || group.title} · Last healthy: ${entry.app.last_healthy_human || 'never'}`"
                      @click="inspectApp(entry.app.name)"
                    >
                      <span
                        class="shrink-0"
                        :class="previewApp === entry.app.name ? 'text-core' : 'text-gold'"
                      >
                        {{ entry.app.name }}
                      </span>
                      <span v-if="entry.detail" class="min-w-0 flex-1 truncate text-muted">
                        {{ entry.detail }}
                      </span>
                      <span v-else class="flex-1"></span>
                      <span
                        class="shrink-0 text-[9px]"
                        :class="entry.app.skipped_unhealthy ? 'text-[#c78a5a]' : 'text-[#ff7b5c]'"
                      >
                        {{ entry.app.skipped_unhealthy ? 'skipped' : 'in cycle' }}
                      </span>
                    </button>
                  </div>
                </template>
              </div>
            </div>
          </div>
        </div>

        <div v-if="config" class="rounded border border-[#3a2016] bg-panel p-3">
          <div class="mb-3 flex items-center justify-between gap-3 font-mono text-[10px] uppercase tracking-[0.18em] text-dim">
            <span>Panel controls</span>
            <span class="text-muted">{{ store.activeDeviceObj?.name ?? store.activeDevice }}</span>
          </div>

          <div class="grid gap-3 sm:grid-cols-[minmax(9.5rem,1fr)_minmax(0,8rem)_minmax(0,7rem)]">
            <div>
              <BrightnessSlider :value="config.brightness" @commit="store.setBrightness" />
              <RouterLink
                v-if="config.brightness_schedule_status"
                to="/devices"
                class="mt-1 inline-block whitespace-nowrap text-[11px] text-gold underline"
                :title="config.brightness_schedule_status === 'custom'
                  ? 'Slider sets the fallback brightness' : 'Slider sets daytime brightness'"
              >
                {{ scheduleLabels[config.brightness_schedule_status] }}
              </RouterLink>
            </div>

            <label class="font-mono text-[10px] uppercase tracking-[0.18em] text-dim">
              Layout
              <select
                :value="config.layout_mode"
                class="mt-2 w-full rounded border border-[#3a2016] bg-[#120a10] px-2 py-1.5 text-xs text-gold focus:border-flame focus:outline-none"
                @change="store.setLayoutMode(($event.target as HTMLSelectElement).value as Config['layout_mode'])"
              >
                <option v-for="mode in layoutModes" :key="mode" :value="mode">{{ mode }}</option>
              </select>
            </label>

            <label class="font-mono text-[10px] uppercase tracking-[0.18em] text-dim">
              Interval
              <input
                type="number"
                min="1"
                max="300"
                :value="config.cycle_interval"
                class="mt-2 w-full rounded border border-[#3a2016] bg-[#120a10] px-2 py-1.5 text-xs text-gold focus:border-flame focus:outline-none"
                @change="store.setCycleInterval(Number(($event.target as HTMLInputElement).value))"
              />
            </label>
          </div>
          <div v-if="config.layout_mode === 'single'" class="mt-3">
            <label class="block font-mono text-[10px] uppercase tracking-[0.18em] text-dim">
              Single app
              <select
                :value="singleAppValue"
                :disabled="singleAppSaving || !singleAppOptions.length"
                class="mt-2 w-full rounded border border-[#3a2016] bg-[#120a10] px-2 py-1.5 text-xs text-gold focus:border-flame focus:outline-none disabled:opacity-60"
                @change="changeSingleApp"
              >
                <option value="">{{ singleAppOptions.length ? 'First available app' : 'No eligible apps' }}</option>
                <option v-for="app in singleAppOptions" :key="app.name" :value="app.name">
                  {{ app.name.replaceAll('_', ' ') }}
                </option>
              </select>
            </label>
            <p v-if="singleAppError" role="alert" class="mt-1 text-xs text-gold">{{ singleAppError }}</p>
          </div>
        </div>
        <div>
          <div class="mb-2 flex flex-wrap items-center justify-between gap-2 font-mono text-[10px] uppercase tracking-[0.18em] text-dim">
            <div class="flex flex-wrap items-center gap-1.5">
              <span>Rotation · {{ rotation.length }}</span>
              <span
                v-if="skippedRotationCount > 0"
                class="rounded border border-[#8a4d22] bg-[#241309] px-1.5 py-0.5 text-[9px] text-[#f0a552]"
                :title="`${skippedRotationCount} enabled app${skippedRotationCount === 1 ? '' : 's'} currently auto-skipped while data is down`"
              >
                {{ skippedRotationCount }} skipped
              </span>
              <span
                v-if="downInCycleCount > 0"
                class="rounded border border-[#b3241a] bg-[#2a0a0e] px-1.5 py-0.5 text-[9px] text-[#ff6a4a]"
                :title="`${downInCycleCount} enabled app${downInCycleCount === 1 ? '' : 's'} unhealthy but still cycling`"
              >
                {{ downInCycleCount }} down
              </span>
            </div>
            <div class="flex items-center gap-3">
              <button class="hover:text-gold" :class="showDisabled ? 'text-gold' : ''" @click="showDisabled = !showDisabled">
                {{ showDisabled ? '− hide disabled' : '+ show disabled' }}
              </button>
              <span :title="skippedRotationCount > 0 ? `${cyclingRotationCount} cycling · ${skippedRotationCount} skipped` : undefined">
                on {{ enabledRotationCount }}
              </span>
            </div>
          </div>
          <ul class="rounded border border-[#3a2016]">
            <AppRow
              v-for="a in visibleRotation"
              :key="a.name"
              :app="a"
              :selected="a.name === previewApp"
              :playing="a.name === nowPlaying"
              @select="store.select(a.name)"
              @show="store.showNow(a.name)"
              @toggle="store.toggle(a)"
            />
          </ul>
          <p v-if="!rotation.length && online" class="mt-2 px-1 font-mono text-[11px] text-dim">No apps registered yet.</p>
        </div>
      </section>
    </div>
  </div>
</template>
