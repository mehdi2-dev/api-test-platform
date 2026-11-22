<script setup>
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import api from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const canEdit = computed(() => auth.hasRole('admin', 'tester'))

const AUTH_LABELS = { none: '—', bearer: 'Bearer', basic: 'Basic', api_key: 'API Key' }

const items = ref([])
const search = ref('')
const loading = ref(false)
const error = ref('')
const notice = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get('/apis', { params: search.value ? { q: search.value } : {} })
    items.value = data
  } catch (err) {
    error.value = errorMessage(err, 'API listesi yüklenemedi')
  } finally {
    loading.value = false
  }
}

async function remove(item) {
  if (!window.confirm(`"${item.name}" silinsin mi? Bu işlem geri alınamaz.`)) return
  error.value = ''
  try {
    await api.delete(`/apis/${item.id}`)
    notice.value = `"${item.name}" silindi`
    await load()
  } catch (err) {
    error.value = errorMessage(err, 'Silinemedi')
  }
}

function formatDate(value) {
  return new Date(value).toLocaleString('tr-TR', { dateStyle: 'short', timeStyle: 'short' })
}

onMounted(load)
</script>

<template>
  <section>
    <header class="page-header">
      <h1>API'ler</h1>
      <RouterLink v-if="canEdit" to="/apis/new" class="btn" data-testid="api-new">
        + Yeni API
      </RouterLink>
    </header>

    <form class="search-row" @submit.prevent="load">
      <input v-model="search" placeholder="Ada göre ara…" data-testid="api-search" />
      <button type="submit" class="btn-secondary" :disabled="loading">Ara</button>
    </form>

    <p v-if="notice" class="form-notice">{{ notice }}</p>
    <p v-if="error" class="form-error">{{ error }}</p>

    <div class="card table-card">
      <table class="table" data-testid="api-table">
        <thead>
          <tr>
            <th>Ad</th>
            <th>Metod</th>
            <th>URL</th>
            <th>Kimlik</th>
            <th>Güncelleme</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in items" :key="item.id">
            <td>
              <RouterLink :to="`/apis/${item.id}`" class="link">{{ item.name }}</RouterLink>
            </td>
            <td>
              <span class="method" :class="`method--${item.method.toLowerCase()}`">
                {{ item.method }}
              </span>
            </td>
            <td class="url-cell" :title="item.url">{{ item.url }}</td>
            <td class="muted">{{ AUTH_LABELS[item.auth.type] }}</td>
            <td class="muted">{{ formatDate(item.updated_at) }}</td>
            <td class="actions">
              <button
                v-if="canEdit"
                class="btn-small btn-danger"
                :data-testid="`api-delete-${item.id}`"
                @click="remove(item)"
              >
                Sil
              </button>
            </td>
          </tr>
          <tr v-if="!loading && items.length === 0">
            <td colspan="6" class="muted">
              Henüz API tanımı yok.
              <RouterLink v-if="canEdit" to="/apis/new" class="link">İlkini ekle</RouterLink>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
