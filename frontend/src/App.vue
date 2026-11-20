<script setup>
import { RouterLink, RouterView } from 'vue-router'
</script>

<template>
  <div class="layout">
    <aside class="sidebar">
      <div class="brand">API Test<br /><span>Platformu</span></div>
      <nav>
        <RouterLink to="/">Genel Bakış</RouterLink>
        <span class="nav-soon" title="Sprint 1 – ATOP-25">API'ler</span>
        <span class="nav-soon" title="ATOP-29">Ortamlar</span>
        <span class="nav-soon" title="ATOP-37">Koleksiyonlar</span>
        <span class="nav-soon" title="ATOP-46">Test Geçmişi</span>
      </nav>
    </aside>
    <main class="content">
      <RouterView />
    </main>
  </div>
</template>
