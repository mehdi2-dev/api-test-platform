<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import api from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useAuthStore } from '@/stores/auth'
import { useEnvironmentStore } from '@/stores/environment'

const auth = useAuthStore()
const envStore = useEnvironmentStore()
const canEdit = computed(() => auth.hasRole('admin', 'tester'))

const RUN_LABELS = { passed: 'Geçti', failed: 'Kaldı', error: 'Hata' }
const STATE_LABELS = { queued: 'Kuyrukta', running: 'Çalışıyor' }
const PRESETS = [
  { cron: '*/5 * * * *', label: '5 dakikada bir' },
  { cron: '0 * * * *', label: 'Saat başı' },
  { cron: '0 9 * * *', label: 'Her gün 09:00' },
  { cron: '0 9 * * 1-5', label: 'Hafta içi 09:00' },
  { cron: '0 3 * * 1', label: 'Pazartesi 03:00' },
]

const schedules = ref([])
const collections = ref([])
const loading = ref(false)
const error = ref('')
const notice = ref('')

const emptyForm = () => ({
  collection_id: '',
  cron: '0 9 * * 1-5',
  environment_id: '',
  enabled: true,
  confirm_production: false,
})
const form = reactive(emptyForm())
const formError = ref('')
const saving = ref(false)

// --- Yükleme ---

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [{ data: list }, { data: cols }] = await Promise.all([
      api.get('/schedules'),
      api.get('/collections'),
    ])
    schedules.value = list
    collections.value = cols
  } catch (err) {
    error.value = errorMessage(err, 'Planlar yüklenemedi')
  } finally {
    loading.value = false
  }
}

// Planlar kendiliğinden çalıştığı için listeyi arada bir tazele
let refreshTimer = null
onMounted(() => {
  load()
  envStore.load().catch(() => {})
  refreshTimer = setInterval(load, 30_000)
})
onBeforeUnmount(() => clearInterval(refreshTimer))

// --- Cron önizleme ---

const preview = ref([])
const previewError = ref('')
let previewTimer = null

watch(
  () => form.cron,
  (value) => {
    clearTimeout(previewTimer)
    previewTimer = setTimeout(async () => {
      if (!value.trim()) {
        preview.value = []
        previewError.value = ''
        return
      }
      try {
        const { data } = await api.get('/schedules/preview', { params: { cron: value, count: 3 } })
        preview.value = data.next_runs
        previewError.value = ''
      } catch (err) {
        preview.value = []
        previewError.value = errorMessage(err, 'Geçersiz ifade')
      }
    }, 300)
  },
  { immediate: true },
)

const selectedEnv = computed(() =>
  envStore.items.find((env) => env.id === Number(form.environment_id)),
)

// --- İşlemler ---

async function create() {
  formError.value = ''
  notice.value = ''
  saving.value = true
  try {
    await api.post('/schedules', {
      collection_id: Number(form.collection_id),
      cron: form.cron,
      environment_id: form.environment_id ? Number(form.environment_id) : null,
      enabled: form.enabled,
      confirm_production: form.confirm_production,
    })
    notice.value = 'Plan oluşturuldu'
    Object.assign(form, emptyForm())
    await load()
  } catch (err) {
    formError.value = errorMessage(err, 'Plan oluşturulamadı')
  } finally {
    saving.value = false
  }
}

async function toggle(schedule) {
  error.value = ''
  try {
    const { data } = await api.patch(`/schedules/${schedule.id}`, { enabled: !schedule.enabled })
    Object.assign(schedule, data)
  } catch (err) {
    error.value = errorMessage(err, 'Güncellenemedi')
  }
}

async function runNow(schedule) {
  error.value = ''
  notice.value = ''
  try {
    await api.post(`/schedules/${schedule.id}/run-now`)
    notice.value = `"${schedule.collection_name}" kuyruğa alındı. Sonucu koleksiyon sayfasında izleyebilirsiniz.`
    await load()
  } catch (err) {
    error.value = errorMessage(err, 'Çalıştırılamadı')
  }
}

async function remove(schedule) {
  if (!window.confirm(`"${schedule.collection_name}" planı silinsin mi?`)) return
  error.value = ''
  try {
    await api.delete(`/schedules/${schedule.id}`)
    await load()
  } catch (err) {
    error.value = errorMessage(err, 'Silinemedi')
  }
}

function formatTime(value) {
  return value
    ? new Date(value).toLocaleString('tr-TR', {
        weekday: 'short',
        day: '2-digit',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
      })
    : '—'
}

function lastRunLabel(schedule) {
  if (!schedule.last_run_state) return null
  return schedule.last_run_state === 'completed'
    ? RUN_LABELS[schedule.last_run_status]
    : STATE_LABELS[schedule.last_run_state]
}

function lastRunClass(schedule) {
  return schedule.last_run_state === 'completed'
    ? `run--${schedule.last_run_status}`
    : `run--${schedule.last_run_state}`
}
</script>

<template>
  <section>
    <header class="page-header">
      <h1>Zamanlamalar</h1>
      <button class="btn-secondary" :disabled="loading" @click="load">Yenile</button>
    </header>

    <p class="muted hint">
      Koleksiyonları belirli zamanlarda otomatik çalıştırın. Zaman <b>cron</b> ifadesiyle yazılır
      (Europe/Istanbul saatiyle): <code>dakika saat gün ay haftanın-günü</code>.
    </p>

    <form v-if="canEdit" class="card form-card" data-testid="schedule-form" @submit.prevent="create">
      <h2>Yeni plan</h2>
      <div class="form-grid">
        <label>
          Koleksiyon
          <select v-model="form.collection_id" required data-testid="schedule-collection">
            <option value="" disabled>seçin…</option>
            <option v-for="c in collections" :key="c.id" :value="c.id">{{ c.name }}</option>
          </select>
        </label>
        <label>
          Ortam
          <select v-model="form.environment_id" data-testid="schedule-env">
            <option value="">Ortam yok</option>
            <option v-for="env in envStore.items" :key="env.id" :value="env.id">
              {{ env.name }}{{ env.is_production ? ' (PROD)' : '' }}
            </option>
          </select>
        </label>
        <label>
          Cron ifadesi
          <input v-model="form.cron" required class="mono" data-testid="schedule-cron" />
        </label>
      </div>

      <div class="cron-presets">
        <span class="muted small-text">Hazır:</span>
        <button
          v-for="p in PRESETS"
          :key="p.cron"
          type="button"
          class="btn-small btn-secondary"
          :class="{ 'preset--active': form.cron === p.cron }"
          @click="form.cron = p.cron"
        >
          {{ p.label }}
        </button>
      </div>

      <p v-if="previewError" class="form-error small-text">{{ previewError }}</p>
      <p v-else-if="preview.length" class="muted small-text" data-testid="cron-preview">
        Sonraki çalışmalar: {{ preview.map(formatTime).join(' · ') }}
      </p>

      <label v-if="selectedEnv?.is_production" class="checkbox">
        <input v-model="form.confirm_production" type="checkbox" data-testid="schedule-confirm" />
        <span>
          <span class="badge badge--prod">PROD</span> Bu ortamda veri değiştiren (POST/PUT/PATCH/DELETE)
          adımların çalışmasına izin veriyorum
        </span>
      </label>
      <label class="checkbox">
        <input v-model="form.enabled" type="checkbox" /> Hemen etkin olsun
      </label>

      <p v-if="formError" class="form-error" data-testid="schedule-error">{{ formError }}</p>
      <button type="submit" :disabled="saving || !!previewError" data-testid="schedule-submit">
        {{ saving ? 'Kaydediliyor…' : 'Planı oluştur' }}
      </button>
    </form>

    <p v-if="notice" class="form-notice">{{ notice }}</p>
    <p v-if="error" class="form-error">{{ error }}</p>

    <div class="card table-card">
      <table class="table" data-testid="schedule-table">
        <thead>
          <tr>
            <th>Koleksiyon</th>
            <th>Cron</th>
            <th>Ortam</th>
            <th>Sonraki çalışma</th>
            <th>Son çalışma</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in schedules" :key="s.id" :class="{ 'row-inactive': !s.enabled }">
            <td>
              <RouterLink :to="`/collections/${s.collection_id}`" class="link">
                {{ s.collection_name }}
              </RouterLink>
            </td>
            <td><code>{{ s.cron }}</code></td>
            <td>
              {{ s.environment_name ?? '—' }}
              <span v-if="s.is_production" class="badge badge--prod">PROD</span>
            </td>
            <td>
              <span v-if="s.enabled">{{ formatTime(s.next_run_at) }}</span>
              <span v-else class="badge badge--inactive">Pasif</span>
            </td>
            <td>
              <template v-if="lastRunLabel(s)">
                <span class="run-badge" :class="lastRunClass(s)">{{ lastRunLabel(s) }}</span>
                <span class="muted small-text"> {{ formatTime(s.last_run_at) }}</span>
              </template>
              <span v-else class="muted">henüz yok</span>
            </td>
            <td class="actions">
              <template v-if="canEdit">
                <button class="btn-small btn-secondary" :data-testid="`run-now-${s.id}`" @click="runNow(s)">
                  Şimdi çalıştır
                </button>
                <button class="btn-small btn-secondary" :data-testid="`toggle-${s.id}`" @click="toggle(s)">
                  {{ s.enabled ? 'Durdur' : 'Etkinleştir' }}
                </button>
                <button class="btn-small btn-danger" @click="remove(s)">Sil</button>
              </template>
            </td>
          </tr>
          <tr v-if="!loading && schedules.length === 0">
            <td colspan="6" class="muted">Henüz plan yok.</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
