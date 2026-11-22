<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import api from '@/api/client'
import { errorCode, errorMessage } from '@/api/errors'
import KeyValueEditor from '@/components/KeyValueEditor.vue'
import { useAuthStore } from '@/stores/auth'
import { useEnvironmentStore } from '@/stores/environment'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const envStore = useEnvironmentStore()
const canEdit = computed(() => auth.hasRole('admin', 'tester'))

const METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS']
const AUTH_TYPES = [
  { value: 'none', label: 'Yok' },
  { value: 'bearer', label: 'Bearer Token' },
  { value: 'basic', label: 'Basic Auth' },
  { value: 'api_key', label: 'API Key' },
]
// Backend gizli değerleri bu şekilde maskeli döndürür
const MASK = '********'
const SECRET_FIELDS = ['token', 'password', 'key_value']

const emptyAuth = () => ({
  type: 'none',
  token: '',
  username: '',
  password: '',
  key_name: '',
  key_value: '',
  location: 'header',
})
const emptyForm = () => ({
  name: '',
  description: '',
  method: 'GET',
  url: '',
  headers: [{ key: 'Accept', value: 'application/json', enabled: true }],
  query_params: [],
  body_type: 'none',
  body: '',
  auth: emptyAuth(),
})

const form = reactive(emptyForm())
const tab = ref('params')
const loading = ref(false)
const saving = ref(false)
const sending = ref(false)
const error = ref('')
const notice = ref('')
const result = ref(null)
const resultTab = ref('body')
let loadedId = null
// Kayıtlı (maskeli) gizli değeri olan alanlar; boş bırakılırsa maske geri konur
const savedSecrets = new Set()

const isNew = computed(() => !route.params.id)

// --- Yükleme ---

function fill(data) {
  const authData = Object.fromEntries(Object.entries(data.auth).map(([k, v]) => [k, v ?? '']))
  savedSecrets.clear()
  for (const field of SECRET_FIELDS) {
    if (authData[field] === MASK) savedSecrets.add(field)
  }
  Object.assign(form, {
    name: data.name,
    description: data.description ?? '',
    method: data.method,
    url: data.url,
    headers: data.headers,
    query_params: data.query_params,
    body_type: data.body_type,
    body: data.body ?? '',
    auth: { ...emptyAuth(), ...authData },
  })
}

async function load() {
  const id = Number(route.params.id)
  if (!isNew.value && id === loadedId) return // az önce kaydettiğimiz kayıt, tekrar çekmeye gerek yok
  error.value = ''
  notice.value = ''
  if (isNew.value) {
    loadedId = null
    Object.assign(form, emptyForm())
    savedSecrets.clear()
    result.value = null
    return
  }
  loading.value = true
  result.value = null
  try {
    const { data } = await api.get(`/apis/${id}`)
    fill(data)
    loadedId = id
  } catch (err) {
    error.value = errorMessage(err, 'API tanımı yüklenemedi')
  } finally {
    loading.value = false
  }
}

watch(() => route.params.id, load, { immediate: true })

// --- Body (JSON doğrulama) ---

const jsonError = computed(() => {
  if (form.body_type !== 'json' || !form.body.trim()) return ''
  try {
    JSON.parse(form.body)
    return ''
  } catch (err) {
    return err.message
  }
})

function formatJson() {
  if (!jsonError.value && form.body.trim()) {
    form.body = JSON.stringify(JSON.parse(form.body), null, 2)
  }
}

// --- Kimlik doğrulama ---

function onAuthTypeChange() {
  // Tip değişince eski tipin maskeli değerleri anlamsız olur
  for (const field of SECRET_FIELDS) {
    if (form.auth[field] === MASK) form.auth[field] = ''
  }
  savedSecrets.clear()
}

// Maskeli alana tıklanınca temizle; hiçbir şey yazılmadan çıkılırsa maskeyi geri koy
function clearMask(field) {
  if (form.auth[field] === MASK) form.auth[field] = ''
}

function restoreMask(field) {
  if (!form.auth[field] && savedSecrets.has(field)) form.auth[field] = MASK
}

// --- Kaydetme ve gönderme ---

function buildPayload() {
  const rows = (list) =>
    list
      .filter((row) => row.key.trim())
      .map((row) => ({ key: row.key.trim(), value: row.value, enabled: row.enabled }))

  const a = form.auth
  const authPayload = { type: a.type }
  if (a.type === 'bearer') authPayload.token = a.token
  if (a.type === 'basic') Object.assign(authPayload, { username: a.username, password: a.password })
  if (a.type === 'api_key') {
    Object.assign(authPayload, { key_name: a.key_name, key_value: a.key_value, location: a.location })
  }

  return {
    name: form.name.trim(),
    description: form.description.trim() || null,
    method: form.method,
    url: form.url.trim(),
    headers: rows(form.headers),
    query_params: rows(form.query_params),
    body_type: form.body_type,
    body: form.body_type === 'none' ? null : form.body,
    auth: authPayload,
  }
}

async function save() {
  error.value = ''
  notice.value = ''
  if (jsonError.value) {
    error.value = `Body geçerli bir JSON değil: ${jsonError.value}`
    tab.value = 'body'
    return null
  }
  saving.value = true
  try {
    let data
    if (isNew.value) {
      ;({ data } = await api.post('/apis', buildPayload()))
      loadedId = data.id
      router.replace(`/apis/${data.id}`)
    } else {
      ;({ data } = await api.patch(`/apis/${route.params.id}`, buildPayload()))
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

async function send() {
  const saved = await save()
  if (!saved) return
  notice.value = ''
  sending.value = true
  const options = { environment_id: envStore.activeId }
  try {
    try {
      const { data } = await api.post(`/apis/${saved.id}/send`, options)
      result.value = data
    } catch (err) {
      // Production koruması: veri değiştiren istek için kullanıcıdan açık onay iste
      if (errorCode(err) !== 'production_confirmation_required') throw err
      if (!window.confirm(errorMessage(err))) {
        notice.value = 'İstek gönderilmedi'
        return
      }
      const { data } = await api.post(`/apis/${saved.id}/send`, {
        ...options,
        confirm_production: true,
      })
      result.value = data
    }
    resultTab.value = 'body'
  } catch (err) {
    error.value = errorMessage(err, 'İstek gönderilemedi')
  } finally {
    sending.value = false
  }
}

// --- Kullanılan değişkenler ve aktif ortam ---

const PLACEHOLDER = /\{\{\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*\}\}/g

const usedVariables = computed(() => {
  const texts = [
    form.url,
    form.body_type === 'none' ? '' : form.body,
    ...form.headers.flatMap((row) => (row.enabled ? [row.key, row.value] : [])),
    ...form.query_params.flatMap((row) => (row.enabled ? [row.key, row.value] : [])),
    ...['token', 'username', 'password', 'key_name', 'key_value'].map((f) => form.auth[f]),
  ]
  const names = new Set()
  for (const text of texts) {
    for (const match of (text ?? '').matchAll(PLACEHOLDER)) names.add(match[1])
  }
  return [...names].sort()
})

const activeKeys = computed(() => new Set((envStore.active?.variables ?? []).map((v) => v.key)))

// --- Sonuç ---

const statusClass = computed(() => {
  const code = result.value?.status_code
  if (!code) return 'status--error'
  if (code < 300) return 'status--ok'
  if (code < 400) return 'status--info'
  if (code < 500) return 'status--warn'
  return 'status--error'
})

const prettyBody = computed(() => {
  if (!result.value) return ''
  const { body_json: bodyJson, body } = result.value
  return bodyJson !== null && bodyJson !== undefined ? JSON.stringify(bodyJson, null, 2) : body
})

function formatSize(bytes) {
  return bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} KB`
}

const enabledCount = (list) => list.filter((row) => row.enabled && row.key.trim()).length
</script>

<template>
  <section>
    <RouterLink to="/apis" class="link back-link">← API'ler</RouterLink>
    <header class="page-header">
      <h1>{{ isNew ? 'Yeni API' : form.name || 'API' }}</h1>
    </header>

    <p v-if="!canEdit" class="muted">Görüntüleme modundasınız; değişiklik yapamazsınız.</p>
    <p v-if="loading" class="muted">Yükleniyor…</p>

    <form class="card api-form" data-testid="api-form" @submit.prevent="save">
      <fieldset :disabled="!canEdit || saving">
        <div class="form-grid">
          <label>
            Ad
            <input v-model="form.name" required maxlength="150" data-testid="api-name" />
          </label>
          <label>
            Açıklama
            <input v-model="form.description" maxlength="1000" data-testid="api-description" />
          </label>
        </div>

        <div class="request-line">
          <select v-model="form.method" class="method-select" data-testid="api-method">
            <option v-for="m in METHODS" :key="m" :value="m">{{ m }}</option>
          </select>
          <input
            v-model="form.url"
            required
            placeholder="https://ornek.com/api/kullanicilar"
            data-testid="api-url"
          />
        </div>
      </fieldset>

      <div class="env-line" data-testid="env-line">
        <span class="muted">Ortam:</span>
        <template v-if="envStore.active">
          <b>{{ envStore.active.name }}</b>
          <span v-if="envStore.active.is_production" class="badge badge--prod">PROD</span>
        </template>
        <span v-else class="muted">seçilmedi (sol menüden seçin)</span>
        <template v-if="usedVariables.length">
          <span class="muted">· Değişkenler:</span>
          <span
            v-for="name in usedVariables"
            :key="name"
            class="var-chip"
            :class="activeKeys.has(name) ? 'var-chip--ok' : 'var-chip--missing'"
            :title="activeKeys.has(name) ? 'Aktif ortamda tanımlı' : 'Aktif ortamda yok'"
          >
            {{ name }}
          </span>
        </template>
      </div>

      <nav class="tabs">
        <button
          type="button"
          :class="{ 'tab--active': tab === 'params' }"
          @click="tab = 'params'"
        >
          Params <span class="muted">({{ enabledCount(form.query_params) }})</span>
        </button>
        <button
          type="button"
          :class="{ 'tab--active': tab === 'headers' }"
          @click="tab = 'headers'"
        >
          Headers <span class="muted">({{ enabledCount(form.headers) }})</span>
        </button>
        <button type="button" :class="{ 'tab--active': tab === 'body' }" @click="tab = 'body'">
          Body
        </button>
        <button type="button" :class="{ 'tab--active': tab === 'auth' }" @click="tab = 'auth'">
          Kimlik doğrulama
        </button>
      </nav>

      <fieldset v-show="tab === 'params'" class="tab-panel" :disabled="!canEdit || saving">
        <p class="muted hint">URL'nin sonuna <code>?anahtar=değer</code> olarak eklenir.</p>
        <KeyValueEditor
          v-model="form.query_params"
          :readonly="!canEdit"
          key-placeholder="Parametre"
          testid="params"
        />
      </fieldset>

      <fieldset v-show="tab === 'headers'" class="tab-panel" :disabled="!canEdit || saving">
        <p class="muted hint">
          Token gibi gizli değerleri buraya değil, <b>Kimlik doğrulama</b> sekmesine yazın; orada
          şifreli saklanır.
        </p>
        <KeyValueEditor
          v-model="form.headers"
          :readonly="!canEdit"
          key-placeholder="Header"
          testid="headers"
        />
      </fieldset>

      <fieldset v-show="tab === 'body'" class="tab-panel" :disabled="!canEdit || saving">
        <div class="radio-row">
          <label v-for="t in ['none', 'json', 'text']" :key="t" class="radio">
            <input v-model="form.body_type" type="radio" :value="t" />
            {{ t === 'none' ? 'Yok' : t === 'json' ? 'JSON' : 'Metin' }}
          </label>
          <button
            v-if="form.body_type === 'json' && canEdit"
            type="button"
            class="btn-small btn-secondary"
            :disabled="!!jsonError"
            @click="formatJson"
          >
            Biçimlendir
          </button>
        </div>
        <template v-if="form.body_type !== 'none'">
          <textarea
            v-model="form.body"
            class="code-input"
            rows="10"
            spellcheck="false"
            :class="{ 'input-invalid': jsonError }"
            :placeholder="form.body_type === 'json' ? '{ &quot;ad&quot;: &quot;Ayşe&quot; }' : ''"
            data-testid="api-body"
          ></textarea>
          <p v-if="jsonError" class="form-error" data-testid="json-error">
            Geçersiz JSON: {{ jsonError }}
          </p>
          <p v-else-if="form.body_type === 'json' && form.body.trim()" class="form-notice small">
            ✓ Geçerli JSON
          </p>
        </template>
        <p v-if="form.body_type !== 'none' && ['GET', 'HEAD'].includes(form.method)" class="muted">
          Not: {{ form.method }} isteklerinde body genelde kullanılmaz.
        </p>
      </fieldset>

      <fieldset v-show="tab === 'auth'" class="tab-panel" :disabled="!canEdit || saving">
        <div class="form-grid">
          <label>
            Tip
            <select v-model="form.auth.type" data-testid="auth-type" @change="onAuthTypeChange">
              <option v-for="t in AUTH_TYPES" :key="t.value" :value="t.value">{{ t.label }}</option>
            </select>
          </label>

          <label v-if="form.auth.type === 'bearer'">
            Token
            <input
              v-model="form.auth.token"
              type="password"
              autocomplete="off"
              data-testid="auth-token"
              @focus="clearMask('token')"
                @blur="restoreMask('token')"
            />
          </label>

          <template v-if="form.auth.type === 'basic'">
            <label>
              Kullanıcı adı
              <input v-model="form.auth.username" autocomplete="off" />
            </label>
            <label>
              Şifre
              <input
                v-model="form.auth.password"
                type="password"
                autocomplete="off"
                @focus="clearMask('password')"
                @blur="restoreMask('password')"
              />
            </label>
          </template>

          <template v-if="form.auth.type === 'api_key'">
            <label>
              Anahtar adı
              <input v-model="form.auth.key_name" placeholder="X-API-Key" />
            </label>
            <label>
              Anahtar değeri
              <input
                v-model="form.auth.key_value"
                type="password"
                autocomplete="off"
                @focus="clearMask('key_value')"
                @blur="restoreMask('key_value')"
              />
            </label>
            <label>
              Nereye eklensin?
              <select v-model="form.auth.location">
                <option value="header">Header</option>
                <option value="query">Query parametresi</option>
              </select>
            </label>
          </template>
        </div>
        <p v-if="SECRET_FIELDS.some((f) => form.auth[f] === MASK)" class="muted hint">
          🔒 Kayıtlı gizli değer şifreli saklanıyor ve gösterilmiyor. Değiştirmek için alana
          tıklayıp yeni değeri yazın; dokunmazsanız eskisi korunur.
        </p>
      </fieldset>

      <p v-if="error" class="form-error" data-testid="api-error">{{ error }}</p>
      <p v-if="notice" class="form-notice" data-testid="api-notice">{{ notice }}</p>

      <div v-if="canEdit" class="form-actions">
        <button
          type="button"
          :disabled="saving || sending"
          data-testid="api-send"
          @click="send"
        >
          {{ sending ? 'Gönderiliyor…' : 'Kaydet ve Gönder' }}
        </button>
        <button type="submit" class="btn-secondary" :disabled="saving" data-testid="api-save">
          {{ saving ? 'Kaydediliyor…' : 'Kaydet' }}
        </button>
      </div>
    </form>

    <div v-if="result" class="card result-card" data-testid="api-result">
      <div class="result-summary">
        <span v-if="result.status_code" class="status-pill" :class="statusClass">
          {{ result.status_code }}
        </span>
        <span v-else class="status-pill status--error">Cevap yok</span>
        <span><b>{{ result.elapsed_ms }}</b> ms</span>
        <span v-if="result.environment" class="muted">Ortam: {{ result.environment }}</span>
        <span v-if="result.ok" class="muted">{{ formatSize(result.size_bytes) }}</span>
      </div>

      <p v-if="result.error" class="form-error" data-testid="result-error">{{ result.error }}</p>

      <nav class="tabs">
        <button :class="{ 'tab--active': resultTab === 'body' }" @click="resultTab = 'body'">
          Cevap
        </button>
        <button :class="{ 'tab--active': resultTab === 'headers' }" @click="resultTab = 'headers'">
          Cevap header'ları
        </button>
        <button :class="{ 'tab--active': resultTab === 'request' }" @click="resultTab = 'request'">
          Gönderilen istek
        </button>
      </nav>

      <pre v-if="resultTab === 'body'" class="code-block" data-testid="result-body">{{
        prettyBody || '(boş cevap)'
      }}</pre>
      <p v-if="resultTab === 'body' && result.truncated" class="muted">
        Cevap çok uzun olduğu için kısaltıldı.
      </p>

      <table v-if="resultTab === 'headers'" class="table compact">
        <tbody>
          <tr v-for="(value, key) in result.headers" :key="key">
            <th>{{ key }}</th>
            <td>{{ value }}</td>
          </tr>
        </tbody>
      </table>

      <div v-if="resultTab === 'request'">
        <p>
          <span class="method" :class="`method--${result.request.method.toLowerCase()}`">
            {{ result.request.method }}
          </span>
          <code class="break">{{ result.request.url }}</code>
        </p>
        <table class="table compact">
          <tbody>
            <tr v-for="(value, key) in result.request.headers" :key="key">
              <th>{{ key }}</th>
              <td>{{ value }}</td>
            </tr>
          </tbody>
        </table>
        <p class="muted small">Gizli değerler (token, şifre, API anahtarı) maskelenmiştir.</p>
      </div>
    </div>
  </section>
</template>
