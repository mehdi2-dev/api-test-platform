<script setup>
import { computed, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { ROLE_LABELS, useAuthStore } from '@/stores/auth'
import { useEnvironmentStore } from '@/stores/environment'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const envStore = useEnvironmentStore()

const blankLayout = computed(() => route.meta.layout === 'blank')
// /apis/5 gibi alt sayfalarda da menüdeki "API'ler" seçili görünsün
const inApis = computed(() => route.path.startsWith('/apis'))
const inCollections = computed(() => route.path.startsWith('/collections'))

// Giriş yapılınca ortam listesini yükle (sol menüdeki seçici için)
watch(
  () => auth.user?.id,
  (id) => {
    if (id) envStore.load().catch(() => {})
    else envStore.reset()
  },
  { immediate: true },
)

function onEnvChange(event) {
  const value = event.target.value
  envStore.setActive(value ? Number(value) : null)
}

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
        <RouterLink to="/environments" data-testid="nav-environments">Ortamlar</RouterLink>
        <RouterLink
          to="/collections"
          data-testid="nav-collections"
          :class="{ 'nav-active': inCollections }"
        >
          Koleksiyonlar
        </RouterLink>
        <RouterLink to="/schedules" data-testid="nav-schedules">Zamanlamalar</RouterLink>
        <span class="nav-soon" title="ATOP-46">Test Geçmişi</span>
      </nav>

      <div v-if="auth.user" class="env-picker">
        <label>
          Aktif ortam
          <select :value="envStore.activeId ?? ''" data-testid="env-picker" @change="onEnvChange">
            <option value="">Ortam yok</option>
            <option v-for="env in envStore.items" :key="env.id" :value="env.id">
              {{ env.name }}{{ env.is_production ? ' (PROD)' : '' }}
            </option>
          </select>
        </label>
        <span v-if="envStore.active?.is_production" class="badge badge--prod">PRODUCTION</span>
      </div>

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
