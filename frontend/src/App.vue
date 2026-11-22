<script setup>
import { computed } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { ROLE_LABELS, useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const blankLayout = computed(() => route.meta.layout === 'blank')
// /apis/5 gibi alt sayfalarda da menüdeki "API'ler" seçili görünsün
const inApis = computed(() => route.path.startsWith('/apis'))

function logout() {
  auth.logout()
  router.push({ name: 'login' })
}
</script>

<template>
  <RouterView v-if="blankLayout" />

  <div v-else class="layout">
    <aside class="sidebar">
      <div class="brand">API Test<br /><span>Platformu</span></div>

      <nav>
        <RouterLink to="/" data-testid="nav-home">Genel Bakış</RouterLink>
        <RouterLink v-if="auth.hasRole('admin')" to="/users" data-testid="nav-users">
          Kullanıcılar
        </RouterLink>
        <RouterLink to="/apis" data-testid="nav-apis" :class="{ 'nav-active': inApis }">
          API'ler
        </RouterLink>
        <span class="nav-soon" title="ATOP-29">Ortamlar</span>
        <span class="nav-soon" title="ATOP-37">Koleksiyonlar</span>
        <span class="nav-soon" title="ATOP-46">Test Geçmişi</span>
      </nav>

      <div v-if="auth.user" class="user-box" data-testid="user-box">
        <div class="user-name">{{ auth.user.full_name }}</div>
        <div class="user-email">{{ auth.user.email }}</div>
        <span class="badge" :class="`badge--${auth.user.role}`">
          {{ ROLE_LABELS[auth.user.role] }}
        </span>
        <button class="btn-link" data-testid="logout" @click="logout">Çıkış yap</button>
      </div>
    </aside>

    <main class="content">
      <RouterView />
    </main>
  </div>
</template>
