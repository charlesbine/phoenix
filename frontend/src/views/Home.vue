<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useMatrixStore } from '@/stores/matrix'
import MatrixPreview from '@/components/MatrixPreview.vue'
import BrightnessSlider from '@/components/BrightnessSlider.vue'
import AppRow from '@/components/AppRow.vue'

const store = useMatrixStore()
const { rotation, config, nowPlaying, nowPlayingLive, online, tick, note, previewApp, selectedApp, following } =
  storeToRefs(store)

const showDisabled = ref(false)
const visibleRotation = computed(() =>
  showDisabled.value ? rotation.value : rotation.value.filter((a) => a.enabled),
)
const previewLive = computed(() => selectedApp.value?.is_live ?? (following.value && nowPlayingLive.value))

onMounted(() => {
  void store.refresh()
  store.connect()
})
onUnmounted(() => store.disconnect())

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
          <button class="ml-auto rounded px-2.5 py-1" :class="selectedApp.enabled ? 'text-flame' : 'text-[#7a4a34]'" @click="store.toggle(selectedApp)">
            {{ selectedApp.enabled ? 'enabled' : 'disabled' }}
          </button>
        </div>
      </section>

      <!-- rotation -->
      <section class="flex flex-col gap-4">
        <BrightnessSlider v-if="config" :value="config.brightness" @commit="store.setBrightness" />
        <div>
          <div class="mb-2 flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.18em] text-dim">
            <span>Rotation · {{ rotation.length }}</span>
            <div class="flex items-center gap-3">
              <button class="hover:text-gold" :class="showDisabled ? 'text-gold' : ''" @click="showDisabled = !showDisabled">
                {{ showDisabled ? '− hide disabled' : '+ show disabled' }}
              </button>
              <span>on {{ rotation.filter((a) => a.enabled).length }}</span>
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
