<template>
  <div id="app">
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
            class="nav-btn"
          >
            <i :class="item.icon"></i>
            {{ item.label }}
          </router-link>
        </nav>

        <!-- Settings -->
        <router-link to="/settings" class="nav-btn">
          <i class="fas fa-cog"></i>
          Settings
        </router-link>
      </div>
    </header>

    <!-- Alert Container -->
    <div v-if="alert" class="alert-container-fixed">
      <div :class="`alert alert-${alert.type}`">
        <span>{{ alert.message }}</span>
        <button class="alert-close" @click="alert = null">
          <i class="fas fa-times"></i>
        </button>
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
  { path: '/screening',  icon: 'fas fa-search',         label: 'Screening'  },
  { path: '/evaluation', icon: 'fas fa-chart-bar',       label: 'Evaluation' },
  { path: '/extraction', icon: 'fas fa-table',           label: 'Extraction' },
  { path: '/quality',    icon: 'fas fa-clipboard-check', label: 'Quality'    },
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
