<script setup lang="ts">
import { onMounted } from 'vue'
import { RouterView } from 'vue-router'
import AppNav from '@/components/AppNav.vue'
import { useMatrixStore } from '@/stores/matrix'

// Populate the device switcher once for the whole app.
onMounted(() => void useMatrixStore().loadDevices())
</script>

<template>
  <div class="scanlines min-h-full">
    <div class="mx-auto max-w-5xl px-5 py-6">
      <AppNav />
      <main class="mt-6">
        <RouterView />
      </main>
    </div>
  </div>
</template>
