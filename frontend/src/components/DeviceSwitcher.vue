<script setup lang="ts">
import { onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { useMatrixStore } from '@/stores/matrix'

const store = useMatrixStore()
onMounted(() => void store.loadDevices())

function onPick(e: Event): void {
  void store.setActiveDevice((e.target as HTMLSelectElement).value)
}
</script>

<template>
  <div class="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.18em]">
    <span class="text-dim">panel</span>
    <div class="relative">
      <select
        :value="store.activeDevice"
        class="appearance-none rounded border border-[#3a2016] bg-[#120a10] py-1 pl-2 pr-6 text-gold focus:border-flame focus:outline-none"
        @change="onPick"
      >
        <option v-for="d in store.devices" :key="d.id" :value="d.id">
          {{ d.name }}{{ d.mirror_of ? ' ↻' : '' }}{{ d.enabled ? '' : ' (off)' }}
        </option>
        <option v-if="!store.devices.length" :value="store.activeDevice">main</option>
      </select>
      <span class="pointer-events-none absolute right-1.5 top-1/2 -translate-y-1/2 text-dim">▾</span>
    </div>
    <RouterLink to="/devices" class="px-1 text-dim hover:text-gold" title="Manage panels">⚙</RouterLink>
  </div>
</template>
