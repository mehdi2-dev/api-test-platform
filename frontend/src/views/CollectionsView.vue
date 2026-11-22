<script setup>
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import api from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useAuthStore } from '@/stores/auth'
import { useEnvironmentStore } from '@/stores/environment'

const router = useRouter()
const auth = useAuthStore()
const environments = useEnvironmentStore()
const canEdit = computed(() => auth.hasRole('admin', 'tester'))
const isAdmin = computed(() => auth.hasRole('admin'))
const seeding = ref(false)

const RUN_LABELS = { passed: 'Geçti', failed: 'Kaldı', error: 'Hata' }

const items = ref([])
const loading = ref(false)
const error = ref('')
const notice = ref('')
const fileInput = ref(null)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get('/collections')
    items.value = data
  } catch (err) {
    error.value = errorMessage(err, 'Koleksiyonlar yüklenemedi')
  } finally {
    loading.value = false
  }
}

async function remove(item) {
  if (!window.confirm(`"${item.name}" koleksiyonu silinsin mi? API tanımları silinmez.`)) return
  error.value = ''
  try {
    await api.delete(`/collections/${item.id}`)
    notice.value = `"${item.name}" silindi`
    await load()
  } catch (err) {
    error.value = errorMessage(err, 'Silinemedi')
  }
}

// --- Örnek senaryolar (ATOP-52..55) ---

async function seedDemo() {
  error.value = ''
  notice.value = ''
  seeding.value = true
  try {
    const { data } = await api.post('/collections/seed-demo')
    const created = data.collections.filter((c) => c.created).length
    notice.value = created
      ? `${created} örnek koleksiyon ve "Demo" ortamı yüklendi. Aktif ortam "Demo" yapıldı; bir örneği açıp çalıştırın.`
      : 'Örnekler zaten yüklü.'
    // Sol menüdeki ortam listesi yeni "Demo" ortamını görsün ve onu seçili yapsın
    await environments.load()
    environments.setActive(data.environment_id)
    await load()
  } catch (err) {
    error.value = errorMessage(err, 'Örnekler yüklenemedi')
  } finally {
    seeding.value = false
  }
}

// --- İçe aktarma (ATOP-40) ---

function chooseFile() {
  fileInput.value?.click()
}

async function importFile(event) {
  const file = event.target.files?.[0]
  event.target.value = '' // aynı dosya tekrar seçilebilsin
  if (!file) return
  error.value = ''
  notice.value = ''
  let payload
  try {
    payload = JSON.parse(await file.text())
  } catch {
    error.value = 'Dosya geçerli bir JSON değil'
    return
  }
  try {
    const { data } = await api.post('/collections/import', payload)
    const needed = data.required_variables.length
      ? ` Ortama eklemeniz gereken değişkenler: ${data.required_variables.join(', ')}.`
      : ''
    window.alert(
      `"${data.collection.name}" içe aktarıldı (${data.created_apis} API tanımı oluşturuldu).${needed}`,
    )
    router.push(`/collections/${data.collection.id}`)
  } catch (err) {
    error.value = errorMessage(err, 'İçe aktarılamadı')
  }
}

function formatTime(value) {
  return value ? new Date(value).toLocaleString('tr-TR', { dateStyle: 'short', timeStyle: 'short' }) : ''
}

onMounted(load)
</script>

<template>
  <section>
    <header class="page-header">
      <h1>Koleksiyonlar</h1>
      <div v-if="canEdit" class="header-actions">
        <button
          v-if="isAdmin"
          class="btn-secondary"
          :disabled="seeding"
          data-testid="seed-demo"
          title="Demo CRM servisi için örnek koleksiyonları ve 'Demo' ortamını oluşturur"
          @click="seedDemo"
        >
          {{ seeding ? 'Yükleniyor…' : 'Örnekleri yükle' }}
        </button>
        <button class="btn-secondary" data-testid="collection-import" @click="chooseFile">
          İçe aktar
        </button>
        <RouterLink to="/collections/new" class="btn" data-testid="collection-new">
          + Yeni koleksiyon
        </RouterLink>
        <input
          ref="fileInput"
          type="file"
          accept=".json,application/json"
          hidden
          @change="importFile"
        />
      </div>
    </header>

    <p class="muted hint">
      Birden fazla API'yi sırayla çalışan bir senaryoda birleştirin. Bir adımın cevabından
      (ör. giriş yapınca dönen token) değer alıp sonraki adımlarda <code v-pre>{{token}}</code>
      olarak kullanabilirsiniz.
    </p>

    <p v-if="notice" class="form-notice">{{ notice }}</p>
    <p v-if="error" class="form-error">{{ error }}</p>

    <div class="card table-card">
      <table class="table" data-testid="collection-table">
        <thead>
          <tr>
            <th>Ad</th>
            <th>Adım</th>
            <th>Son çalıştırma</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in items" :key="item.id">
            <td>
              <RouterLink :to="`/collections/${item.id}`" class="link">{{ item.name }}</RouterLink>
              <div v-if="item.description" class="muted small-text">{{ item.description }}</div>
            </td>
            <td>{{ item.item_count }}</td>
            <td>
              <template v-if="item.last_run_status">
                <span class="run-badge" :class="`run--${item.last_run_status}`">
                  {{ RUN_LABELS[item.last_run_status] }}
                </span>
                <span class="muted small-text"> {{ formatTime(item.last_run_at) }}</span>
              </template>
              <span v-else class="muted">henüz yok</span>
            </td>
            <td class="actions">
              <button v-if="canEdit" class="btn-small btn-danger" @click="remove(item)">Sil</button>
            </td>
          </tr>
          <tr v-if="!loading && items.length === 0">
            <td colspan="4" class="muted">Henüz koleksiyon yok.</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
