<template>
  <div id="app">
    <!-- Aurora Background -->
    <div class="aurora-background" aria-hidden="true"></div>

    <!-- Glass Navbar -->
    <header class="app-navbar">
      <div class="navbar-container">
        <!-- Brand -->
        <router-link to="/" class="navbar-brand">
          <img src="/logo.svg" alt="MetaScreener" />
          <span>MetaScreener</span>
        </router-link>

        <!-- Nav Links -->
        <nav class="navbar-nav">
          <router-link
            v-for="item in navItems"
            :key="item.path"
            :to="item.path"
            class="nav-link"
          >
            <span>{{ item.icon }}</span>
            {{ item.label }}
          </router-link>
        </nav>

        <!-- Right side -->
        <div style="display: flex; align-items: center; gap: 0.5rem;">
          <router-link to="/settings" class="nav-link">
            ⚙️ Settings
          </router-link>
        </div>
      </div>
    </header>

    <!-- Alert Container -->
    <div id="alert-container" v-if="alert" style="
      position: fixed; top: 68px; left: 50%; transform: translateX(-50%);
      z-index: 999; min-width: 320px; max-width: 600px; padding: 0 1rem;">
      <div :class="`alert alert-${alert.type}`" style="display: flex; align-items: center; justify-content: space-between;">
        <span>{{ alert.message }}</span>
        <button @click="alert = null" style="background: none; border: none; cursor: pointer; font-size: 1.1rem;">✕</button>
      </div>
    </div>

    <!-- Page Content -->
    <main class="page-content">
      <div class="std-container">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" @alert="showAlert" />
          </transition>
        </router-view>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, provide } from 'vue'

const navItems = [
  { path: '/screening', icon: '🔍', label: 'Screening' },
  { path: '/evaluation', icon: '📊', label: 'Evaluation' },
  { path: '/extraction', icon: '📋', label: 'Extraction' },
  { path: '/quality', icon: '✅', label: 'Quality' },
]

interface AlertState {
  message: string
  type: 'success' | 'danger' | 'warning' | 'info'
}

const alert = ref<AlertState | null>(null)

function showAlert(message: string, type: AlertState['type'] = 'danger') {
  alert.value = { message, type }
  setTimeout(() => { alert.value = null }, 5000)
}

// Provide showAlert to child components
provide('showAlert', showAlert)
</script>

<style>
/* Transition */
.fade-enter-active, .fade-leave-active { transition: opacity 0.2s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
