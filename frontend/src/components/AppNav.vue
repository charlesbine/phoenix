<script setup lang="ts">
import { RouterLink } from 'vue-router'
import Wordmark from '@/components/Wordmark.vue'

const links = [
  { to: '/', label: 'Home' },
  { to: '/apps', label: 'Apps' },
  { to: '/panels', label: 'Panels' },
  { to: '/playlists', label: 'Playlists' },
  { to: '/store', label: 'Store' },
]
</script>

<template>
  <header class="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-4">
    <RouterLink to="/" class="shrink-0"><Wordmark :size="28" /></RouterLink>
    <nav class="flex gap-1 font-mono text-[11px] uppercase tracking-wider">
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
  </header>
</template>
