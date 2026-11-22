<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const email = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function submit() {
  error.value = ''
  loading.value = true
  try {
    await auth.login(email.value.trim(), password.value)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    router.push(redirect)
  } catch (err) {
    const status = err.response?.status
    if (status === 401) {
      error.value = err.response.data?.detail ?? 'E-posta veya şifre hatalı'
    } else if (status === 422) {
      error.value = 'Lütfen geçerli bir e-posta adresi girin'
    } else {
      error.value = 'Sunucuya ulaşılamıyor, backend çalışıyor mu?'
    }
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <form class="card login-card" data-testid="login-form" @submit.prevent="submit">
      <h1>API Test Platformu</h1>
      <p class="muted">Devam etmek için giriş yapın</p>

      <label>
        E-posta
        <input
          v-model="email"
          type="email"
          autocomplete="username"
          required
          data-testid="login-email"
        />
      </label>

      <label>
        Şifre
        <input
          v-model="password"
          type="password"
          autocomplete="current-password"
          required
          data-testid="login-password"
        />
      </label>

      <p v-if="error" class="form-error" data-testid="login-error">{{ error }}</p>

      <button type="submit" :disabled="loading" data-testid="login-submit">
        {{ loading ? 'Giriş yapılıyor…' : 'Giriş yap' }}
      </button>
    </form>
  </div>
</template>
