<script setup lang="ts">
import { RouterView } from 'vue-router'
import AppNav from '@/components/AppNav.vue'
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
