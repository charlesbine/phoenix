<script setup lang="ts">
import { RouterLink } from 'vue-router'
import Wordmark from '@/components/Wordmark.vue'
import DeviceSwitcher from '@/components/DeviceSwitcher.vue'

const links = [
  { to: '/', label: 'Home' },
  { to: '/apps', label: 'Apps' },
  { to: '/panels', label: 'Panels' },
  { to: '/playlists', label: 'Playlists' },
  { to: '/store', label: 'Store' },
  { to: '/devices', label: 'Devices' },
  { to: '/diagnostics', label: 'Logs' },
]
</script>

<template>
  <header class="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-4">
    <RouterLink to="/" class="shrink-0"><Wordmark :size="28" /></RouterLink>
    <div class="flex flex-wrap items-center gap-3">
      <DeviceSwitcher />
      <nav class="flex flex-wrap gap-1 font-mono text-[11px] uppercase tracking-wider">
        <RouterLink v-for="l in links" :key="l.to" :to="l.to" custom v-slot="{ isExactActive, navigate }">
          <button
            class="rounded px-2.5 py-1.5"
            :class="isExactActive ? 'bg-[#251009] text-gold' : 'text-dim hover:text-gold'"
            @click="navigate"
          >
            {{ l.label }}
          </button>
        </RouterLink>
      </nav>
    </div>
  </header>
</template>
