<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import api from '@/api/client'
import { errorCode, errorMessage } from '@/api/errors'
import { useAuthStore } from '@/stores/auth'
import { useEnvironmentStore } from '@/stores/environment'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const envStore = useEnvironmentStore()
const canEdit = computed(() => auth.hasRole('admin', 'tester'))

const RUN_LABELS = { passed: 'Geçti', failed: 'Kaldı', error: 'Hata', skipped: 'Atlandı' }
const SOURCES = [
  { value: 'json_path', label: 'JSON alanı' },
  { value: 'header', label: 'Header' },
  { value: 'status_code', label: 'Durum kodu' },
]

const emptyForm = () => ({ name: '', description: '', stop_on_failure: false, items: [] })
const form = reactive(emptyForm())
const allApis = ref([])
const newApiId = ref('')
const loading = ref(false)
const saving = ref(false)
const running = ref(false)
const error = ref('')
const notice = ref('')
const result = ref(null)
const runs = ref([])
const openStep = ref(null) // sonuçta detayı açık olan adım
let loadedId = null

const isNew = computed(() => !route.params.id)

// --- Yükleme ---

function fill(data) {
  Object.assign(form, {
    name: data.name,
    description: data.description ?? '',
    stop_on_failure: data.stop_on_failure,
    items: data.items.map((item) => ({
      api_definition_id: item.api_definition_id,
      api_name: item.api_name,
      method: item.method,
      url: item.url,
      enabled: item.enabled,
      extractions: item.extractions.map((ex) => ({ ...ex, path: ex.path ?? '' })),
    })),
  })
}

async function loadApis() {
  try {
    const { data } = await api.get('/apis')
    allApis.value = data
  } catch {
    allApis.value = []
  }
}

async function loadRuns() {
  if (!loadedId) return
  try {
    const { data } = await api.get(`/collections/${loadedId}/runs`)
    runs.value = data
  } catch {
    runs.value = []
  }
}

async function load() {
  const id = Number(route.params.id)
  if (!isNew.value && id === loadedId) return
  error.value = ''
  notice.value = ''
  result.value = null
  runs.value = []
  if (isNew.value) {
    loadedId = null
    Object.assign(form, emptyForm())
    return
  }
  loading.value = true
  try {
    const { data } = await api.get(`/collections/${id}`)
    fill(data)
    loadedId = id
    await loadRuns()
  } catch (err) {
    error.value = errorMessage(err, 'Koleksiyon yüklenemedi')
  } finally {
    loading.value = false
  }
}

watch(() => route.params.id, load, { immediate: true })
loadApis()

// --- Adımlar: ekleme, sıralama (sürükle-bırak), silme ---

function addStep() {
  const selected = allApis.value.find((a) => a.id === Number(newApiId.value))
  if (!selected) return
  form.items.push({
    api_definition_id: selected.id,
    api_name: selected.name,
    method: selected.method,
    url: selected.url,
    enabled: true,
    extractions: [],
  })
  newApiId.value = ''
}

function removeStep(index) {
  form.items.splice(index, 1)
}

function moveStep(from, to) {
  if (to < 0 || to >= form.items.length || from === to) return
  const [step] = form.items.splice(from, 1)
  form.items.splice(to, 0, step)
}

const dragIndex = ref(null)
const dropIndex = ref(null)

function onDragStart(index, event) {
  dragIndex.value = index
  event.dataTransfer.effectAllowed = 'move'
}

function onDragOver(index) {
  dropIndex.value = index
}

function onDrop(index) {
  if (dragIndex.value !== null) moveStep(dragIndex.value, index)
  dragIndex.value = null
  dropIndex.value = null
}

function onDragEnd() {
  dragIndex.value = null
  dropIndex.value = null
}

// --- Değişken çıkarma ---

function addExtraction(step) {
  step.extractions.push({ variable: '', source: 'json_path', path: '$.', secret: false })
}

function removeExtraction(step, index) {
  step.extractions.splice(index, 1)
}

// --- Kaydet / çalıştır / dışa aktar ---

function payload() {
  return {
    name: form.name.trim(),
    description: form.description.trim() || null,
    stop_on_failure: form.stop_on_failure,
    items: form.items.map((item) => ({
      api_definition_id: item.api_definition_id,
      enabled: item.enabled,
      extractions: item.extractions
        .filter((ex) => ex.variable.trim())
        .map((ex) => ({
          // Kullanıcı yanlışlıkla {{token}} yazarsa süslü parantezleri temizle
          variable: ex.variable.trim().replace(/^\{\{\s*|\s*\}\}$/g, ''),
          source: ex.source,
          path: ex.source === 'status_code' ? null : ex.path.trim(),
          secret: ex.secret,
        })),
    })),
  }
}

async function save() {
  error.value = ''
  notice.value = ''
  saving.value = true
  try {
    let data
    if (isNew.value) {
      ;({ data } = await api.post('/collections', payload()))
      loadedId = data.id
      router.replace(`/collections/${data.id}`)
    } else {
      ;({ data } = await api.patch(`/collections/${loadedId}`, payload()))
    }
    fill(data)
    notice.value = 'Kaydedildi'
    return data
  } catch (err) {
    error.value = errorMessage(err, 'Kaydedilemedi')
    return null
  } finally {
    saving.value = false
  }
}

async function run() {
  const saved = await save()
  if (!saved) return
  notice.value = ''
  running.value = true
  openStep.value = null
  const options = { environment_id: envStore.activeId }
  try {
    try {
      const { data } = await api.post(`/collections/${saved.id}/run`, options)
      result.value = data
    } catch (err) {
      if (errorCode(err) !== 'production_confirmation_required') throw err
      if (!window.confirm(errorMessage(err))) {
        notice.value = 'Koleksiyon çalıştırılmadı'
        return
      }
      const { data } = await api.post(`/collections/${saved.id}/run`, {
        ...options,
        confirm_production: true,
      })
      result.value = data
    }
    await loadRuns()
  } catch (err) {
    error.value = errorMessage(err, 'Koleksiyon çalıştırılamadı')
  } finally {
    running.value = false
  }
}

async function showRun(summary) {
  error.value = ''
  openStep.value = null
  try {
    const { data } = await api.get(`/collections/${loadedId}/runs/${summary.id}`)
    result.value = data
  } catch (err) {
    error.value = errorMessage(err, 'Kayıt açılamadı')
  }
}

async function exportJson() {
  error.value = ''
  try {
    const { data } = await api.get(`/collections/${loadedId}/export`)
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `${data.name.replace(/[^\p{L}\p{N}_-]+/gu, '_')}.json`
    link.click()
    URL.revokeObjectURL(link.href)
    notice.value = data.required_variables.length
      ? `Dışa aktarıldı. Gizli değerler dosyaya yazılmadı; gereken değişkenler: ${data.required_variables.join(', ')}`
      : 'Dışa aktarıldı'
  } catch (err) {
    error.value = errorMessage(err, 'Dışa aktarılamadı')
  }
}

// --- Sonuç ---

function stepRun(step) {
  return step.test_run_id ? result.value?.step_runs?.[step.test_run_id] : null
}

function formatTime(value) {
  return new Date(value).toLocaleString('tr-TR', { dateStyle: 'short', timeStyle: 'medium' })
}

const usableApis = computed(() => allApis.value)
</script>

<template>
  <section>
    <RouterLink to="/collections" class="link back-link">← Koleksiyonlar</RouterLink>
    <header class="page-header">
      <h1>{{ isNew ? 'Yeni koleksiyon' : form.name || 'Koleksiyon' }}</h1>
      <button v-if="!isNew" class="btn-secondary" data-testid="collection-export" @click="exportJson">
        Dışa aktar (JSON)
      </button>
    </header>

    <p v-if="!canEdit" class="muted">Görüntüleme modundasınız; değişiklik yapamazsınız.</p>
    <p v-if="loading" class="muted">Yükleniyor…</p>

    <form class="card api-form" data-testid="collection-form" @submit.prevent="save">
      <fieldset :disabled="!canEdit || saving">
        <div class="form-grid">
          <label>
            Ad
            <input v-model="form.name" required maxlength="150" data-testid="collection-name" />
          </label>
          <label>
            Açıklama
            <input v-model="form.description" maxlength="1000" />
          </label>
        </div>
        <label class="checkbox">
          <input v-model="form.stop_on_failure" type="checkbox" data-testid="stop-on-failure" />
          Bir adım geçemezse <b>dur</b> (kapalıysa kalan adımlar yine çalışır)
        </label>
      </fieldset>

      <div class="env-line">
        <span class="muted">Ortam:</span>
        <template v-if="envStore.active">
          <b>{{ envStore.active.name }}</b>
          <span v-if="envStore.active.is_production" class="badge badge--prod">PROD</span>
        </template>
        <span v-else class="muted">seçilmedi (sol menüden seçin)</span>
      </div>

      <h3>Adımlar</h3>
      <p v-if="canEdit && form.items.length > 1" class="muted hint">
        Sırayı değiştirmek için satırları tutup sürükleyin ya da ↑ ↓ düğmelerini kullanın.
      </p>

      <ol class="steps" data-testid="steps">
        <li
          v-for="(step, i) in form.items"
          :key="i"
          class="step"
          :class="{
            'step--dragging': dragIndex === i,
            'step--drop': dropIndex === i && dragIndex !== i,
            'step--disabled': !step.enabled,
          }"
          :data-testid="`step-${i}`"
          @dragover.prevent="onDragOver(i)"
          @drop.prevent="onDrop(i)"
          @dragend="onDragEnd"
        >
          <div class="step-head">
            <span
              v-if="canEdit"
              class="drag-handle"
              title="Sıralamak için tutup sürükleyin"
              draggable="true"
              @dragstart="onDragStart(i, $event)"
              >⋮⋮</span
            >
            <span class="step-number">{{ i + 1 }}</span>
            <span class="method" :class="`method--${step.method.toLowerCase()}`">{{ step.method }}</span>
            <RouterLink :to="`/apis/${step.api_definition_id}`" class="link step-name">
              {{ step.api_name }}
            </RouterLink>
            <code class="step-url muted">{{ step.url }}</code>
            <span class="step-actions">
              <label class="checkbox small-text" title="Adım çalıştırılsın mı?">
                <input v-model="step.enabled" type="checkbox" :disabled="!canEdit" /> etkin
              </label>
              <template v-if="canEdit">
                <button type="button" class="btn-small btn-secondary" :disabled="i === 0" @click="moveStep(i, i - 1)">↑</button>
                <button
                  type="button"
                  class="btn-small btn-secondary"
                  :disabled="i === form.items.length - 1"
                  @click="moveStep(i, i + 1)"
                >
                  ↓
                </button>
                <button type="button" class="btn-small btn-secondary" title="Adımı kaldır" @click="removeStep(i)">✕</button>
              </template>
            </span>
          </div>

          <div v-if="step.extractions.length || canEdit" class="extractions">
            <div v-for="(ex, j) in step.extractions" :key="j" class="extraction-row">
              <span class="muted small-text">cevaptan al</span>
              <select v-model="ex.source" :disabled="!canEdit">
                <option v-for="s in SOURCES" :key="s.value" :value="s.value">{{ s.label }}</option>
              </select>
              <input
                v-if="ex.source !== 'status_code'"
                v-model="ex.path"
                class="mono"
                :readonly="!canEdit"
                :placeholder="ex.source === 'header' ? 'Location' : '$.access_token'"
                :data-testid="`ex-path-${i}-${j}`"
              />
              <span v-else></span>
              <span class="muted small-text">→</span>
              <input
                v-model="ex.variable"
                class="mono"
                :readonly="!canEdit"
                placeholder="token"
                :data-testid="`ex-var-${i}-${j}`"
              />
              <label class="checkbox small-text" title="Değer sonuçlarda ******** gösterilsin">
                <input v-model="ex.secret" type="checkbox" :disabled="!canEdit" /> gizli
              </label>
              <button
                v-if="canEdit"
                type="button"
                class="btn-small btn-secondary"
                @click="removeExtraction(step, j)"
              >
                ✕
              </button>
            </div>
            <button
              v-if="canEdit"
              type="button"
              class="btn-link-dark small-text"
              :data-testid="`ex-add-${i}`"
              @click="addExtraction(step)"
            >
              + Cevaptan değişken al
            </button>
          </div>
        </li>
      </ol>
      <p v-if="form.items.length === 0" class="muted">Henüz adım yok.</p>

      <div v-if="canEdit" class="add-step">
        <select v-model="newApiId" data-testid="add-step-select">
          <option value="">API seçin…</option>
          <option v-for="a in usableApis" :key="a.id" :value="a.id">{{ a.method }} · {{ a.name }}</option>
        </select>
        <button
          type="button"
          class="btn-secondary"
          :disabled="!newApiId"
          data-testid="add-step"
          @click="addStep"
        >
          + Adım ekle
        </button>
      </div>

      <p v-if="error" class="form-error" data-testid="collection-error">{{ error }}</p>
      <p v-if="notice" class="form-notice">{{ notice }}</p>

      <div v-if="canEdit" class="form-actions">
        <button type="button" :disabled="saving || running" data-testid="collection-run" @click="run">
          {{ running ? 'Çalışıyor…' : 'Kaydet ve Çalıştır' }}
        </button>
        <button type="submit" class="btn-secondary" :disabled="saving" data-testid="collection-save">
          {{ saving ? 'Kaydediliyor…' : 'Kaydet' }}
        </button>
      </div>
    </form>

    <div v-if="result" class="card result-card" data-testid="collection-result">
      <div class="result-summary">
        <span class="run-badge" :class="`run--${result.status}`">{{ RUN_LABELS[result.status] }}</span>
        <span>
          <b>{{ result.passed_steps }}/{{ result.total_steps }}</b> adım geçti
          <span v-if="result.skipped_steps" class="muted">· {{ result.skipped_steps }} atlandı</span>
        </span>
        <span><b>{{ result.elapsed_ms }}</b> ms</span>
        <span v-if="result.environment_name" class="muted">Ortam: {{ result.environment_name }}</span>
      </div>

      <ul class="step-results">
        <li v-for="step in result.steps" :key="step.position" :class="`step-result--${step.status}`">
          <div class="step-result-head" @click="openStep = openStep === step.position ? null : step.position">
            <span class="run-badge" :class="`run--${step.status}`">{{ RUN_LABELS[step.status] }}</span>
            <span class="method" :class="`method--${step.method.toLowerCase()}`">{{ step.method }}</span>
            <b>{{ step.api_name }}</b>
            <template v-if="stepRun(step)">
              <span class="muted">{{ stepRun(step).status_code ?? '—' }}</span>
              <span class="muted">{{ stepRun(step).elapsed_ms }} ms</span>
              <span v-if="stepRun(step).assertion_results.length" class="muted">
                {{ stepRun(step).passed_count }}/{{ stepRun(step).assertion_results.length }} kural
              </span>
            </template>
            <span
              v-for="ex in step.extracted"
              :key="ex.variable"
              class="var-chip"
              :class="ex.found ? 'var-chip--ok' : 'var-chip--missing'"
              :title="ex.found ? `değer: ${ex.value}` : 'cevapta bulunamadı'"
            >
              {{ ex.variable }}{{ ex.found ? ` = ${ex.value}` : ' ✗' }}
            </span>
            <span class="muted expand">{{ openStep === step.position ? '▲' : '▼' }}</span>
          </div>

          <div v-if="openStep === step.position" class="step-result-body">
            <p v-if="step.message" class="form-error">{{ step.message }}</p>
            <ul v-if="stepRun(step)?.assertion_results.length" class="rule-results">
              <li
                v-for="(item, k) in stepRun(step).assertion_results"
                :key="k"
                :class="item.passed ? 'rule--passed' : 'rule--failed'"
              >
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
            <template v-if="stepRun(step)">
              <p class="small-text">
                <code class="break">{{ stepRun(step).request.url }}</code>
              </p>
              <pre v-if="stepRun(step).response" class="code-block">{{ stepRun(step).response.body || '(boş cevap)' }}</pre>
            </template>
          </div>
        </li>
      </ul>
    </div>

    <div v-if="runs.length" class="card runs-card" data-testid="collection-runs">
      <h2>Son çalıştırmalar</h2>
      <table class="table compact runs-table">
        <tbody>
          <tr
            v-for="item in runs"
            :key="item.id"
            :class="{ 'run-row--selected': result && result.id === item.id }"
            @click="showRun(item)"
          >
            <td>
              <span class="run-badge" :class="`run--${item.status}`">{{ RUN_LABELS[item.status] }}</span>
            </td>
            <td>{{ item.passed_steps }}/{{ item.total_steps }} adım</td>
            <td>{{ item.elapsed_ms }} ms</td>
            <td class="muted">{{ item.environment_name ?? 'ortamsız' }}</td>
            <td class="muted">{{ formatTime(item.created_at) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
