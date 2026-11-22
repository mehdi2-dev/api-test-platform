<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { storeToRefs } from 'pinia'
import api from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useSystemStore } from '@/stores/system'

const system = useSystemStore()
const { health, isHealthy } = storeToRefs(system)

const RUN_LABELS = { passed: 'Geçti', failed: 'Kaldı', error: 'Hata' }
const STATE_LABELS = { queued: 'Kuyrukta', running: 'Çalışıyor' }
const labels = { database: 'PostgreSQL', redis: 'Redis' }

const days = ref(7)
const data = ref(null)
const loading = ref(false)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data: result } = await api.get('/dashboard', { params: { days: days.value } })
    data.value = result
  } catch (err) {
    error.value = errorMessage(err, 'Dashboard yüklenemedi')
  } finally {
    loading.value = false
  }
}

function refresh() {
  load()
  system.fetchHealth()
}

watch(days, load)
onMounted(refresh)

// Grafikteki en uzun çubuğun yüksekliği = o dönemdeki en yoğun gün
const maxDaily = computed(() =>
  Math.max(1, ...(data.value?.daily ?? []).map((d) => d.passed + d.failed + d.error)),
)

function barHeight(value) {
  return `${(value / maxDaily.value) * 100}%`
}

function dayLabel(value) {
  return new Date(`${value}T00:00:00`).toLocaleDateString('tr-TR', { day: '2-digit', month: 'short' })
}

function formatTime(value) {
  return new Date(value).toLocaleString('tr-TR', { dateStyle: 'short', timeStyle: 'short' })
}

function rateClass(rate) {
  if (rate === null || rate === undefined) return ''
  if (rate >= 90) return 'kpi--ok'
  if (rate >= 70) return 'kpi--warn'
  return 'kpi--bad'
}

function collectionLabel(run) {
  return run.state === 'completed' ? RUN_LABELS[run.status] : STATE_LABELS[run.state]
}

function collectionClass(run) {
  return run.state === 'completed' ? `run--${run.status}` : `run--${run.state}`
}
</script>

<template>
  <section>
    <header class="page-header">
      <h1>Genel Bakış</h1>
      <div class="header-actions">
        <select v-model.number="days" data-testid="dashboard-days">
          <option :value="1">Bugün</option>
          <option :value="7">Son 7 gün</option>
          <option :value="30">Son 30 gün</option>
        </select>
        <button :disabled="loading" @click="refresh">{{ loading ? 'Yükleniyor…' : 'Yenile' }}</button>
      </div>
    </header>

    <p v-if="error" class="form-error">{{ error }}</p>

    <template v-if="data">
      <div class="kpis" data-testid="kpis">
        <div class="card kpi">
          <div class="kpi-label">Çalıştırma</div>
          <div class="kpi-value">{{ data.totals.runs }}</div>
          <div class="muted small-text">API isteği (tek + koleksiyon adımı)</div>
        </div>
        <div class="card kpi" :class="rateClass(data.totals.success_rate)">
          <div class="kpi-label">Başarı oranı</div>
          <div class="kpi-value">
            {{ data.totals.success_rate === null ? '—' : `%${data.totals.success_rate}` }}
          </div>
          <div class="muted small-text">{{ data.totals.passed }} geçti</div>
        </div>
        <div class="card kpi">
          <div class="kpi-label">Ortalama süre</div>
          <div class="kpi-value">
            {{ data.totals.avg_elapsed_ms === null ? '—' : `${Math.round(data.totals.avg_elapsed_ms)} ms` }}
          </div>
          <div class="muted small-text">cevap alınan istekler</div>
        </div>
        <div class="card kpi" :class="{ 'kpi--bad': data.totals.failed + data.totals.error > 0 }">
          <div class="kpi-label">Başarısız</div>
          <div class="kpi-value">{{ data.totals.failed + data.totals.error }}</div>
          <div class="muted small-text">{{ data.totals.failed }} kaldı · {{ data.totals.error }} hata</div>
        </div>
      </div>

      <div class="card chart-card">
        <h2>Günlük sonuçlar</h2>
        <div class="chart" data-testid="daily-chart">
          <div v-for="d in data.daily" :key="d.date" class="chart-col">
            <div
              class="chart-stack"
              :title="`${dayLabel(d.date)}: ${d.passed} geçti, ${d.failed} kaldı, ${d.error} hata`"
            >
              <div class="bar bar--error" :style="{ height: barHeight(d.error) }"></div>
              <div class="bar bar--failed" :style="{ height: barHeight(d.failed) }"></div>
              <div class="bar bar--passed" :style="{ height: barHeight(d.passed) }"></div>
            </div>
            <div class="chart-label">{{ dayLabel(d.date) }}</div>
          </div>
        </div>
        <div class="legend small-text">
          <span><i class="bar--passed"></i> Geçti</span>
          <span><i class="bar--failed"></i> Kaldı</span>
          <span><i class="bar--error"></i> Hata</span>
        </div>
      </div>

      <div class="dash-grid">
        <div class="card">
          <h2>En çok kalan API'ler</h2>
          <p v-if="!data.failing_apis.length" class="muted">Bu dönemde kalan test yok 🎉</p>
          <table v-else class="table compact">
            <tbody>
              <tr v-for="a in data.failing_apis" :key="`${a.api_definition_id}-${a.api_name}`">
                <td>
                  <RouterLink v-if="a.api_definition_id" :to="`/apis/${a.api_definition_id}`" class="link">
                    {{ a.api_name }}
                  </RouterLink>
                  <span v-else>{{ a.api_name }}</span>
                </td>
                <td class="muted">{{ a.failed }}/{{ a.runs }} kaldı</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="card">
          <h2>En yavaş API'ler</h2>
          <p v-if="!data.slowest_apis.length" class="muted">Veri yok</p>
          <table v-else class="table compact">
            <tbody>
              <tr v-for="a in data.slowest_apis" :key="`${a.api_definition_id}-${a.api_name}`">
                <td>{{ a.api_name }}</td>
                <td class="muted">ort. {{ Math.round(a.avg_elapsed_ms) }} ms</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="dash-grid">
        <div class="card">
          <header class="card-header">
            <h2>Son çalıştırmalar</h2>
            <RouterLink to="/history" class="link small-text">Tüm geçmiş →</RouterLink>
          </header>
          <p v-if="!data.recent_runs.length" class="muted">Henüz çalıştırma yok</p>
          <table v-else class="table compact clickable">
            <tbody>
              <tr v-for="r in data.recent_runs" :key="r.id" @click="$router.push(`/history/${r.id}`)">
                <td><span class="run-badge" :class="`run--${r.status}`">{{ RUN_LABELS[r.status] }}</span></td>
                <td>{{ r.api_name }}</td>
                <td class="muted">{{ r.status_code ?? '—' }}</td>
                <td class="muted">{{ formatTime(r.created_at) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="card">
          <h2>Son koleksiyon çalıştırmaları</h2>
          <p v-if="!data.recent_collection_runs.length" class="muted">Henüz yok</p>
          <table v-else class="table compact clickable">
            <tbody>
              <tr
                v-for="r in data.recent_collection_runs"
                :key="r.id"
                @click="r.collection_id && $router.push(`/collections/${r.collection_id}`)"
              >
                <td><span class="run-badge" :class="collectionClass(r)">{{ collectionLabel(r) }}</span></td>
                <td>
                  {{ r.collection_name }}
                  <span v-if="r.trigger === 'schedule'" class="muted small-text">· zamanlanmış</span>
                </td>
                <td class="muted">{{ r.passed_steps }}/{{ r.total_steps }}</td>
                <td class="muted">{{ formatTime(r.created_at) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <div v-if="health" class="card system-card">
      <span class="dot" :class="isHealthy ? 'dot--ok' : 'dot--error'" />
      <strong>{{ isHealthy ? 'Tüm sistemler çalışıyor' : 'Bazı servisler yanıt vermiyor' }}</strong>
      <span v-for="(value, key) in health.checks" :key="key" class="muted small-text">
        · {{ labels[key] ?? key }}: {{ value === 'ok' ? 'bağlı' : 'hata' }}
      </span>
    </div>
  </section>
</template>
