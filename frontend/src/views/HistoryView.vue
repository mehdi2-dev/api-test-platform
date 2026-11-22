<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useEnvironmentStore } from '@/stores/environment'

const route = useRoute()
const router = useRouter()
const envStore = useEnvironmentStore()

const RUN_LABELS = { passed: 'Geçti', failed: 'Kaldı', error: 'Hata' }
const PAGE_SIZE = 25

// Filtreler adres çubuğunda da tutulur: sayfa yenilense ya da bağlantı paylaşılsa aynı görünüm gelir
const filters = reactive({
  q: route.query.q ?? '',
  status: route.query.status ?? '',
  environment: route.query.environment ?? '',
  source: route.query.source ?? 'all',
  date_from: route.query.date_from ?? '',
  date_to: route.query.date_to ?? '',
})
const page = ref(Number(route.query.page ?? 1))
const result = ref({ total: 0, items: [] })
const loading = ref(false)
const error = ref('')

const pageCount = computed(() => Math.max(1, Math.ceil(result.value.total / PAGE_SIZE)))

function cleanParams() {
  return Object.fromEntries(
    Object.entries(filters).filter(([key, value]) => value && !(key === 'source' && value === 'all')),
  )
}

async function load() {
  loading.value = true
  error.value = ''
  const params = cleanParams()
  router.replace({ query: { ...params, ...(page.value > 1 ? { page: page.value } : {}) } })
  try {
    const { data } = await api.get('/runs/history', {
      params: { ...params, offset: (page.value - 1) * PAGE_SIZE, limit: PAGE_SIZE },
    })
    result.value = data
  } catch (err) {
    error.value = errorMessage(err, 'Geçmiş yüklenemedi')
  } finally {
    loading.value = false
  }
}

function search() {
  page.value = 1
  load()
}

function reset() {
  Object.assign(filters, {
    q: '',
    status: '',
    environment: '',
    source: 'all',
    date_from: '',
    date_to: '',
  })
  search()
}

function goTo(newPage) {
  page.value = newPage
  load()
}

function formatTime(value) {
  return new Date(value).toLocaleString('tr-TR', { dateStyle: 'short', timeStyle: 'medium' })
}

onMounted(() => {
  envStore.load().catch(() => {})
  load()
})
</script>

<template>
  <section>
    <header class="page-header">
      <h1>Test Geçmişi</h1>
      <span class="muted">{{ result.total }} kayıt</span>
    </header>

    <form class="card filters" data-testid="history-filters" @submit.prevent="search">
      <label>
        API adı
        <input v-model="filters.q" placeholder="ara…" data-testid="filter-q" />
      </label>
      <label>
        Sonuç
        <select v-model="filters.status" data-testid="filter-status">
          <option value="">Hepsi</option>
          <option value="passed">Geçti</option>
          <option value="failed">Kaldı</option>
          <option value="error">Hata</option>
        </select>
      </label>
      <label>
        Ortam
        <select v-model="filters.environment">
          <option value="">Hepsi</option>
          <option value="none">Ortamsız</option>
          <option v-for="env in envStore.items" :key="env.id" :value="env.name">{{ env.name }}</option>
        </select>
      </label>
      <label>
        Kaynak
        <select v-model="filters.source">
          <option value="all">Hepsi</option>
          <option value="single">Tek API</option>
          <option value="collection">Koleksiyon adımı</option>
        </select>
      </label>
      <label>
        Başlangıç
        <input v-model="filters.date_from" type="date" />
      </label>
      <label>
        Bitiş
        <input v-model="filters.date_to" type="date" />
      </label>
      <div class="filter-actions">
        <button type="submit" :disabled="loading" data-testid="filter-submit">Filtrele</button>
        <button type="button" class="btn-secondary" @click="reset">Temizle</button>
      </div>
    </form>

    <p v-if="error" class="form-error">{{ error }}</p>

    <div class="card table-card">
      <table class="table clickable" data-testid="history-table">
        <thead>
          <tr>
            <th>Sonuç</th>
            <th>API</th>
            <th>Kod</th>
            <th>Süre</th>
            <th>Kurallar</th>
            <th>Ortam</th>
            <th>Zaman</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in result.items" :key="r.id" @click="$router.push(`/history/${r.id}`)">
            <td><span class="run-badge" :class="`run--${r.status}`">{{ RUN_LABELS[r.status] }}</span></td>
            <td>
              <span class="method" :class="`method--${r.method.toLowerCase()}`">{{ r.method }}</span>
              {{ r.api_name }}
              <span v-if="r.collection_run_id" class="muted small-text">· koleksiyon</span>
            </td>
            <td>{{ r.status_code ?? '—' }}</td>
            <td class="muted">{{ r.elapsed_ms }} ms</td>
            <td class="muted">{{ r.passed_count }}/{{ r.passed_count + r.failed_count }}</td>
            <td class="muted">{{ r.environment_name ?? '—' }}</td>
            <td class="muted">{{ formatTime(r.created_at) }}</td>
          </tr>
          <tr v-if="!loading && result.items.length === 0">
            <td colspan="7" class="muted">Bu filtrelere uyan kayıt yok.</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="pageCount > 1" class="pager">
      <button class="btn-small btn-secondary" :disabled="page <= 1" @click="goTo(page - 1)">← Önceki</button>
      <span class="muted">Sayfa {{ page }} / {{ pageCount }}</span>
      <button class="btn-small btn-secondary" :disabled="page >= pageCount" @click="goTo(page + 1)">
        Sonraki →
      </button>
    </div>
  </section>
</template>
