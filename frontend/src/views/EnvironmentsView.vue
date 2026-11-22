<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import api from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useAuthStore } from '@/stores/auth'
import { useEnvironmentStore } from '@/stores/environment'

const auth = useAuthStore()
const envStore = useEnvironmentStore()
const canEdit = computed(() => auth.hasRole('admin', 'tester'))

// Backend gizli değerleri bu şekilde maskeli döndürür
const MASK = '********'

const selectedId = ref(null) // null + creating=false: hiçbiri seçili değil
const creating = ref(false)
const saving = ref(false)
const error = ref('')
const notice = ref('')

const emptyForm = () => ({ name: '', description: '', is_production: false, variables: [] })
const form = reactive(emptyForm())

const editing = computed(() => creating.value || selectedId.value !== null)

// --- Seçim ---

function toRows(variables) {
  // saved: bu satırın kayıtlı gizli bir değeri var (MASK geri gönderilirse korunur)
  return variables.map((v) => ({ ...v, saved: v.is_secret && v.value === MASK }))
}

function select(env) {
  creating.value = false
  selectedId.value = env.id
  error.value = ''
  notice.value = ''
  Object.assign(form, {
    name: env.name,
    description: env.description ?? '',
    is_production: env.is_production,
    variables: toRows(env.variables),
  })
}

function startCreate() {
  selectedId.value = null
  creating.value = true
  error.value = ''
  notice.value = ''
  Object.assign(form, emptyForm(), {
    variables: [{ key: 'base_url', value: '', is_secret: false, saved: false }],
  })
}

// --- Değişken satırları ---

function addRow() {
  form.variables.push({ key: '', value: '', is_secret: false, saved: false })
}

function removeRow(index) {
  form.variables.splice(index, 1)
}

function onSecretToggle(row) {
  // Gizlilik kapatılırsa maske anlamsız olur; kullanıcı değeri yeniden girmeli
  if (!row.is_secret && row.value === MASK) {
    row.value = ''
    row.saved = false
  }
}

function clearMask(row) {
  if (row.value === MASK) row.value = ''
}

function restoreMask(row) {
  if (!row.value && row.saved && row.is_secret) row.value = MASK
}

// --- Kaydet / sil ---

function payload() {
  return {
    name: form.name.trim(),
    description: form.description.trim() || null,
    is_production: form.is_production,
    variables: form.variables
      .filter((row) => row.key.trim())
      .map((row) => ({ key: row.key.trim(), value: row.value, is_secret: row.is_secret })),
  }
}

async function save() {
  error.value = ''
  notice.value = ''
  saving.value = true
  try {
    const { data } = creating.value
      ? await api.post('/environments', payload())
      : await api.patch(`/environments/${selectedId.value}`, payload())
    await envStore.load()
    select(data)
    notice.value = `"${data.name}" kaydedildi`
  } catch (err) {
    error.value = errorMessage(err, 'Kaydedilemedi')
  } finally {
    saving.value = false
  }
}

async function remove() {
  const name = form.name
  if (!window.confirm(`"${name}" ortamı ve tüm değişkenleri silinsin mi?`)) return
  error.value = ''
  try {
    await api.delete(`/environments/${selectedId.value}`)
    selectedId.value = null
    await envStore.load()
    notice.value = `"${name}" silindi`
  } catch (err) {
    error.value = errorMessage(err, 'Silinemedi')
  }
}

onMounted(async () => {
  try {
    await envStore.load()
    const first = envStore.active ?? envStore.items[0]
    if (first) select(first)
  } catch (err) {
    error.value = errorMessage(err, 'Ortamlar yüklenemedi')
  }
})
</script>

<template>
  <section>
    <header class="page-header">
      <h1>Ortamlar</h1>
      <button v-if="canEdit" data-testid="env-new" @click="startCreate">+ Yeni ortam</button>
    </header>

    <p class="muted hint">
      API adreslerinde <code v-pre>{{base_url}}</code> gibi değişkenler kullanın; istek
      gönderilirken sol menüde seçili ortamın değerleri yerine konur.
    </p>

    <p v-if="notice" class="form-notice">{{ notice }}</p>

    <div class="env-layout">
      <ul class="env-list" data-testid="env-list">
        <li
          v-for="env in envStore.items"
          :key="env.id"
          :class="{ 'env-item--selected': env.id === selectedId }"
          class="env-item"
          @click="select(env)"
        >
          <div class="env-item-title">
            {{ env.name }}
            <span v-if="env.is_production" class="badge badge--prod">PROD</span>
          </div>
          <div class="muted small-text">
            {{ env.variables.length }} değişken
            <span v-if="env.id === envStore.activeId"> · <b>aktif</b></span>
          </div>
        </li>
        <li v-if="envStore.loaded && envStore.items.length === 0" class="muted env-empty">
          Henüz ortam yok.
        </li>
      </ul>

      <form
        v-if="editing"
        class="card api-form env-form"
        data-testid="env-form"
        @submit.prevent="save"
      >
        <h2>{{ creating ? 'Yeni ortam' : form.name }}</h2>

        <fieldset :disabled="!canEdit || saving">
          <div class="form-grid">
            <label>
              Ad
              <input v-model="form.name" required maxlength="100" data-testid="env-name" />
            </label>
            <label>
              Açıklama
              <input v-model="form.description" maxlength="1000" />
            </label>
          </div>

          <label class="checkbox">
            <input v-model="form.is_production" type="checkbox" data-testid="env-prod" />
            Bu bir <b>Production</b> ortamı (veri değiştiren istekler onay ister)
          </label>

          <h3>Değişkenler</h3>
          <div class="var-head muted">
            <span>Ad</span><span>Değer</span><span>Gizli</span><span></span>
          </div>
          <div v-for="(row, i) in form.variables" :key="i" class="var-row">
            <input v-model="row.key" placeholder="base_url" :data-testid="`var-key-${i}`" />
            <input
              v-model="row.value"
              :type="row.is_secret ? 'password' : 'text'"
              autocomplete="off"
              :placeholder="row.is_secret ? 'gizli değer' : 'https://dev.ornek.com'"
              :data-testid="`var-value-${i}`"
              @focus="clearMask(row)"
              @blur="restoreMask(row)"
            />
            <input
              v-model="row.is_secret"
              type="checkbox"
              title="Değer şifreli saklanır ve ekranda gösterilmez"
              @change="onSecretToggle(row)"
            />
            <button
              v-if="canEdit"
              type="button"
              class="btn-small btn-secondary"
              title="Değişkeni sil"
              @click="removeRow(i)"
            >
              ✕
            </button>
          </div>
          <p v-if="form.variables.length === 0" class="muted">Değişken yok.</p>
          <button
            v-if="canEdit"
            type="button"
            class="btn-small btn-secondary add-var"
            data-testid="var-add"
            @click="addRow"
          >
            + Değişken ekle
          </button>
        </fieldset>

        <p v-if="error" class="form-error" data-testid="env-error">{{ error }}</p>

        <div class="form-actions">
          <button v-if="canEdit" type="submit" :disabled="saving" data-testid="env-save">
            {{ saving ? 'Kaydediliyor…' : 'Kaydet' }}
          </button>
          <button
            v-if="!creating && selectedId !== envStore.activeId"
            type="button"
            class="btn-secondary"
            data-testid="env-activate"
            @click="envStore.setActive(selectedId)"
          >
            Aktif ortam yap
          </button>
          <button
            v-if="canEdit && !creating"
            type="button"
            class="btn-danger"
            data-testid="env-delete"
            @click="remove"
          >
            Sil
          </button>
        </div>
      </form>

      <p v-else-if="error" class="form-error">{{ error }}</p>
    </div>
  </section>
</template>
