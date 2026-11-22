<script setup>
import { onMounted, reactive, ref } from 'vue'
import api from '@/api/client'
import { ROLE_LABELS, useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

const users = ref([])
const loading = ref(false)
const error = ref('')
const notice = ref('')

const emptyForm = () => ({ email: '', full_name: '', password: '', role: 'tester' })
const form = reactive(emptyForm())
const formError = ref('')
const saving = ref(false)

const roleOptions = Object.entries(ROLE_LABELS).map(([value, label]) => ({ value, label }))

// Backend'in hata mesajını okunur hale getirir (tek mesaj veya doğrulama listesi)
function errorMessage(err, fallback) {
  const detail = err.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((d) => `${d.loc?.at(-1)}: ${d.msg}`).join(' · ')
  return fallback
}

function isSelf(user) {
  return user.id === auth.user?.id
}

async function loadUsers() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get('/users')
    users.value = data
  } catch (err) {
    error.value = errorMessage(err, 'Kullanıcılar yüklenemedi')
  } finally {
    loading.value = false
  }
}

async function createUser() {
  formError.value = ''
  notice.value = ''
  saving.value = true
  try {
    const { data } = await api.post('/users', { ...form })
    notice.value = `${data.email} eklendi`
    Object.assign(form, emptyForm())
    await loadUsers()
  } catch (err) {
    formError.value = errorMessage(err, 'Kullanıcı eklenemedi')
  } finally {
    saving.value = false
  }
}

async function updateUser(user, changes) {
  error.value = ''
  notice.value = ''
  try {
    const { data } = await api.patch(`/users/${user.id}`, changes)
    Object.assign(user, data)
    notice.value = `${data.email} güncellendi`
  } catch (err) {
    error.value = errorMessage(err, 'Kullanıcı güncellenemedi')
    await loadUsers()
  }
}

function formatDate(value) {
  return new Date(value).toLocaleDateString('tr-TR')
}

onMounted(loadUsers)
</script>

<template>
  <section>
    <header class="page-header">
      <h1>Kullanıcılar</h1>
      <button class="btn-secondary" :disabled="loading" @click="loadUsers">Yenile</button>
    </header>

    <form class="card form-card" data-testid="user-form" @submit.prevent="createUser">
      <h2>Yeni kullanıcı</h2>
      <div class="form-grid">
        <label>
          Ad soyad
          <input v-model="form.full_name" required maxlength="100" data-testid="new-name" />
        </label>
        <label>
          E-posta
          <input v-model="form.email" type="email" required data-testid="new-email" />
        </label>
        <label>
          Şifre (en az 8 karakter)
          <input
            v-model="form.password"
            type="password"
            required
            minlength="8"
            autocomplete="new-password"
            data-testid="new-password"
          />
        </label>
        <label>
          Rol
          <select v-model="form.role" data-testid="new-role">
            <option v-for="r in roleOptions" :key="r.value" :value="r.value">{{ r.label }}</option>
          </select>
        </label>
      </div>
      <p v-if="formError" class="form-error" data-testid="form-error">{{ formError }}</p>
      <button type="submit" :disabled="saving" data-testid="new-submit">
        {{ saving ? 'Ekleniyor…' : 'Kullanıcı ekle' }}
      </button>
    </form>

    <p v-if="notice" class="form-notice" data-testid="notice">{{ notice }}</p>
    <p v-if="error" class="form-error" data-testid="list-error">{{ error }}</p>

    <div class="card table-card">
      <table class="table" data-testid="users-table">
        <thead>
          <tr>
            <th>Ad soyad</th>
            <th>E-posta</th>
            <th>Rol</th>
            <th>Durum</th>
            <th>Eklenme</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="u in users" :key="u.id" :class="{ 'row-inactive': !u.is_active }">
            <td>
              {{ u.full_name }}
              <span v-if="isSelf(u)" class="muted small">(siz)</span>
            </td>
            <td>{{ u.email }}</td>
            <td>
              <select
                :value="u.role"
                :disabled="isSelf(u)"
                :title="isSelf(u) ? 'Kendi rolünüzü değiştiremezsiniz' : ''"
                @change="updateUser(u, { role: $event.target.value })"
              >
                <option v-for="r in roleOptions" :key="r.value" :value="r.value">
                  {{ r.label }}
                </option>
              </select>
            </td>
            <td>
              <span class="badge" :class="u.is_active ? 'badge--active' : 'badge--inactive'">
                {{ u.is_active ? 'Aktif' : 'Pasif' }}
              </span>
            </td>
            <td class="muted">{{ formatDate(u.created_at) }}</td>
            <td class="actions">
              <button
                v-if="!isSelf(u)"
                class="btn-small"
                :class="u.is_active ? 'btn-danger' : 'btn-secondary'"
                @click="updateUser(u, { is_active: !u.is_active })"
              >
                {{ u.is_active ? 'Pasifleştir' : 'Aktifleştir' }}
              </button>
            </td>
          </tr>
          <tr v-if="!loading && users.length === 0">
            <td colspan="6" class="muted">Henüz kullanıcı yok</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
