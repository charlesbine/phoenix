import { createRouter, createWebHistory } from 'vue-router'
import Home from '@/views/Home.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: Home },
    { path: '/apps', component: () => import('@/views/Apps.vue') },
    { path: '/panels', component: () => import('@/views/Panels.vue') },
    { path: '/playlists', component: () => import('@/views/Playlists.vue') },
    { path: '/store', component: () => import('@/views/Store.vue') },
    { path: '/devices', component: () => import('@/views/Devices.vue') },
    { path: '/diagnostics', component: () => import('@/views/Diagnostics.vue') },
  ],
})
