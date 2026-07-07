<script setup lang="ts">
import { onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { useMatrixStore } from '@/stores/matrix'

const store = useMatrixStore()
onMounted(() => void store.loadDevices())
</script>

<template>
  <div class="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.18em]">
    <span class="text-dim">panel</span>
    <button
      v-for="d in store.devices"
      :key="d.id"
      class="rounded px-2.5 py-1"
      :class="[
        d.id === store.activeDevice ? 'bg-flame text-[#160a0a]' : 'text-dim hover:text-gold',
        d.enabled ? '' : 'opacity-50',
      ]"
      :title="d.enabled ? d.name : `${d.name} (off)`"
      @click="store.setActiveDevice(d.id)"
    >
      {{ d.name }}{{ d.mirror_of ? ' ↻' : '' }}
    </button>
    <RouterLink to="/devices" class="px-1 text-dim hover:text-gold" title="Manage panels">⚙</RouterLink>
  </div>
</template>
