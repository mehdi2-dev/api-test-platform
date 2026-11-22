<script setup>
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import api from '@/api/client'
import { errorMessage } from '@/api/errors'
import { lineDiff, prettyJson } from '@/utils/diff'

const route = useRoute()

const RUN_LABELS = { passed: 'Geçti', failed: 'Kaldı', error: 'Hata' }

const run = ref(null)
const baseline = ref(null)
const tab = ref('response')
const error = ref('')
const copied = ref(false)

async function load() {
  error.value = ''
  run.value = null
  baseline.value = null
  try {
    const id = route.params.id
    const [{ data }, { data: previous }] = await Promise.all([
      api.get(`/runs/${id}`),
      api.get(`/runs/${id}/baseline`),
    ])
    run.value = data
    baseline.value = previous
    tab.value = data.status === 'passed' ? 'response' : 'report'
  } catch (err) {
    error.value = errorMessage(err, 'Kayıt yüklenemedi')
  }
}

watch(() => route.params.id, load, { immediate: true })

// Kalan kurallar önce gösterilir: hata raporunda göz ilk oraya gitsin
const sortedRules = computed(() =>
  [...(run.value?.assertion_results ?? [])].sort((a, b) => Number(a.passed) - Number(b.passed)),
)
const failedRules = computed(() => sortedRules.value.filter((rule) => !rule.passed))

const body = computed(() => prettyJson(run.value?.response?.body ?? ''))
const baselineBody = computed(() => prettyJson(baseline.value?.response?.body ?? ''))
const diff = computed(() => (baseline.value ? lineDiff(baselineBody.value, body.value) : []))
const changedLines = computed(() => diff.value.filter((line) => line.type !== 'same').length)

function formatTime(value) {
  return new Date(value).toLocaleString('tr-TR', { dateStyle: 'medium', timeStyle: 'medium' })
}

// Jira'ya / Slack'e yapıştırılabilir hata raporu (ATOP-47)
const reportText = computed(() => {
  const r = run.value
  if (!r) return ''
  const lines = [
    `Hata raporu: ${r.method} ${r.api_name} — ${RUN_LABELS[r.status]}`,
    '',
    `Ortam: ${r.environment_name ?? 'ortamsız'}`,
    `Zaman: ${formatTime(r.created_at)}`,
    `İstek: ${r.request.method} ${r.request.url}`,
    `Durum kodu: ${r.status_code ?? 'cevap yok'} · Süre: ${r.elapsed_ms} ms`,
  ]
  if (r.error) lines.push(`Hata: ${r.error}`)
  if (failedRules.value.length) {
    lines.push('', 'Kalan kurallar:')
    for (const rule of failedRules.value) {
      const target = rule.target ? ` ${rule.target}` : ''
      const expected = rule.expected !== null ? ` ${rule.expected}` : ''
      const actual = rule.actual !== null ? ` (gelen: ${rule.actual})` : ''
      lines.push(`- ${rule.type}${target} ${rule.operator}${expected}: ${rule.message}${actual}`)
    }
  }
  if (baseline.value) {
    lines.push(
      '',
      `Son başarılı çalıştırma: ${formatTime(baseline.value.created_at)} · ` +
        `${baseline.value.status_code} · ${baseline.value.elapsed_ms} ms`,
    )
  }
  if (r.response?.body) {
    lines.push('', 'Cevap (ilk 1000 karakter):', r.response.body.slice(0, 1000))
  }
  lines.push('', `Kayıt: ${window.location.href}`)
  return lines.join('\n')
})

async function copyReport() {
  try {
    await navigator.clipboard.writeText(reportText.value)
    copied.value = true
    setTimeout(() => (copied.value = false), 2000)
  } catch {
    error.value = 'Panoya kopyalanamadı; metni elle seçip kopyalayın'
  }
}
</script>

<template>
  <section>
    <RouterLink to="/history" class="link back-link">← Test Geçmişi</RouterLink>
    <p v-if="error" class="form-error">{{ error }}</p>

    <template v-if="run">
      <header class="page-header">
        <h1>
          <span class="method" :class="`method--${run.method.toLowerCase()}`">{{ run.method }}</span>
          {{ run.api_name }}
        </h1>
        <button class="btn-secondary" data-testid="copy-report" @click="copyReport">
          {{ copied ? 'Kopyalandı ✓' : 'Hata raporunu kopyala' }}
        </button>
      </header>

      <div class="card result-summary detail-summary">
        <span class="run-badge" :class="`run--${run.status}`">{{ RUN_LABELS[run.status] }}</span>
        <span v-if="run.status_code" class="status-pill">{{ run.status_code }}</span>
        <span><b>{{ run.elapsed_ms }}</b> ms</span>
        <span class="muted">{{ run.passed_count }}/{{ run.passed_count + run.failed_count }} kural</span>
        <span class="muted">Ortam: {{ run.environment_name ?? '—' }}</span>
        <span class="muted">{{ formatTime(run.created_at) }}</span>
        <RouterLink v-if="run.api_definition_id" :to="`/apis/${run.api_definition_id}`" class="link">
          API'yi aç →
        </RouterLink>
      </div>

      <p v-if="run.error" class="form-error">{{ run.error }}</p>

      <div class="card">
        <h2>Kurallar</h2>
        <p v-if="!sortedRules.length" class="muted">Bu çalıştırmada kural yoktu.</p>
        <ul class="rule-results">
          <li v-for="(item, i) in sortedRules" :key="i" :class="item.passed ? 'rule--passed' : 'rule--failed'">
            <span class="rule-icon">{{ item.passed ? '✓' : '✗' }}</span>
            <div>
              <b>{{ item.type }}</b>
              <code v-if="item.target">{{ item.target }}</code>
              {{ item.operator }}
              <code v-if="item.expected !== null">{{ item.expected }}</code>
              <div class="muted small-text">
                {{ item.message }}<template v-if="item.actual !== null">
                  · gelen: <code>{{ item.actual }}</code></template
                >
              </div>
            </div>
          </li>
        </ul>
      </div>

      <div class="card result-card">
        <nav class="tabs">
          <button :class="{ 'tab--active': tab === 'report' }" @click="tab = 'report'">Hata raporu</button>
          <button :class="{ 'tab--active': tab === 'response' }" @click="tab = 'response'">Cevap</button>
          <button :class="{ 'tab--active': tab === 'compare' }" data-testid="tab-compare" @click="tab = 'compare'">
            Önceki başarılıyla karşılaştır
          </button>
          <button :class="{ 'tab--active': tab === 'request' }" @click="tab = 'request'">İstek</button>
          <button :class="{ 'tab--active': tab === 'headers' }" @click="tab = 'headers'">Cevap header'ları</button>
        </nav>

        <pre v-if="tab === 'report'" class="code-block report-block" data-testid="report-text">{{ reportText }}</pre>

        <template v-if="tab === 'response'">
          <p v-if="!run.response" class="muted">Cevap alınamadı.</p>
          <pre v-else class="code-block">{{ body || '(boş cevap)' }}</pre>
          <p v-if="run.response?.truncated" class="muted">Cevap kısaltılarak saklandı.</p>
        </template>

        <div v-if="tab === 'compare'" data-testid="compare">
          <p v-if="!baseline" class="muted">
            Bu API'nin bundan önce başarılı bir çalıştırması yok; karşılaştırılacak kayıt bulunamadı.
          </p>
          <template v-else>
            <table class="table compact compare-table">
              <thead>
                <tr>
                  <th></th>
                  <th>
                    Son başarılı
                    <RouterLink :to="`/history/${baseline.id}`" class="link small-text">
                      ({{ formatTime(baseline.created_at) }})
                    </RouterLink>
                  </th>
                  <th>Bu çalıştırma</th>
                </tr>
              </thead>
              <tbody>
                <tr :class="{ changed: baseline.status_code !== run.status_code }">
                  <th>Durum kodu</th>
                  <td>{{ baseline.status_code }}</td>
                  <td>{{ run.status_code ?? 'cevap yok' }}</td>
                </tr>
                <tr>
                  <th>Süre</th>
                  <td>{{ baseline.elapsed_ms }} ms</td>
                  <td>{{ run.elapsed_ms }} ms</td>
                </tr>
                <tr :class="{ changed: baseline.request.url !== run.request.url }">
                  <th>URL</th>
                  <td><code class="break">{{ baseline.request.url }}</code></td>
                  <td><code class="break">{{ run.request.url }}</code></td>
                </tr>
                <tr :class="{ changed: baseline.environment_name !== run.environment_name }">
                  <th>Ortam</th>
                  <td>{{ baseline.environment_name ?? '—' }}</td>
                  <td>{{ run.environment_name ?? '—' }}</td>
                </tr>
              </tbody>
            </table>
            <p class="muted small-text">
              Cevap gövdesi farkı: {{ changedLines ? `${changedLines} satır değişmiş` : 'aynı' }}
              <span class="diff-legend"><i class="diff--removed"></i> önceki <i class="diff--added"></i> şimdiki</span>
            </p>
            <pre class="code-block diff-block"><span
                v-for="(line, i) in diff"
                :key="i"
                class="diff-line"
                :class="`diff--${line.type}`"
              >{{ line.type === 'added' ? '+ ' : line.type === 'removed' ? '- ' : '  ' }}{{ line.text }}</span></pre>
          </template>
        </div>

        <div v-if="tab === 'request'">
          <p>
            <span class="method" :class="`method--${run.request.method.toLowerCase()}`">{{ run.request.method }}</span>
            <code class="break">{{ run.request.url }}</code>
          </p>
          <table class="table compact">
            <tbody>
              <tr v-for="(value, key) in run.request.headers" :key="key">
                <th>{{ key }}</th>
                <td>{{ value }}</td>
              </tr>
            </tbody>
          </table>
          <p class="muted small">Gizli değerler maskelenmiştir.</p>
        </div>

        <table v-if="tab === 'headers'" class="table compact">
          <tbody>
            <tr v-for="(value, key) in run.response?.headers ?? {}" :key="key">
              <th>{{ key }}</th>
              <td>{{ value }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </section>
</template>
