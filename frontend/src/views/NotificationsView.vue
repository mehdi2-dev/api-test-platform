<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import api from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const isAdmin = computed(() => auth.hasRole('admin'))

const TYPES = {
  slack: { label: 'Slack', placeholder: 'https://hooks.slack.com/services/…' },
  teams: { label: 'Microsoft Teams', placeholder: 'https://…webhook.office.com/…' },
  webhook: { label: 'Webhook (JSON)', placeholder: 'https://ornek.com/bildirim' },
  email: { label: 'E-posta', placeholder: 'qa@firma.com, lead@firma.com' },
}

const channels = ref([])
const loading = ref(false)
const error = ref('')
const notice = ref('')

const emptyForm = () => ({ name: '', type: 'slack', target: '', notify_on: 'failure' })
const form = reactive(emptyForm())
const formError = ref('')
const saving = ref(false)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get('/notifications')
    channels.value = data
  } catch (err) {
    error.value = errorMessage(err, 'Kanallar yüklenemedi')
  } finally {
    loading.value = false
  }
}

async function create() {
  formError.value = ''
  notice.value = ''
  saving.value = true
  try {
    await api.post('/notifications', { ...form })
    notice.value = `"${form.name}" eklendi. "Deneme gönder" ile kontrol edin.`
    Object.assign(form, emptyForm())
    await load()
  } catch (err) {
    formError.value = errorMessage(err, 'Kanal eklenemedi')
  } finally {
    saving.value = false
  }
}

async function update(channel, changes) {
  error.value = ''
  try {
    const { data } = await api.patch(`/notifications/${channel.id}`, changes)
    Object.assign(channel, data)
  } catch (err) {
    error.value = errorMessage(err, 'Güncellenemedi')
  }
}

async function sendTest(channel) {
  error.value = ''
  notice.value = ''
  try {
    const { data } = await api.post(`/notifications/${channel.id}/test`)
    if (data.ok) notice.value = `"${channel.name}" kanalına deneme bildirimi gönderildi`
    else error.value = `"${channel.name}": ${data.error}`
    await load()
  } catch (err) {
    error.value = errorMessage(err, 'Gönderilemedi')
  }
}

async function remove(channel) {
  if (!window.confirm(`"${channel.name}" kanalı silinsin mi?`)) return
  try {
    await api.delete(`/notifications/${channel.id}`)
    await load()
  } catch (err) {
    error.value = errorMessage(err, 'Silinemedi')
  }
}

function formatTime(value) {
  return value ? new Date(value).toLocaleString('tr-TR', { dateStyle: 'short', timeStyle: 'short' }) : '—'
}

onMounted(load)
</script>

<template>
  <section>
    <header class="page-header">
      <h1>Bildirimler</h1>
    </header>

    <p class="muted hint">
      Bir koleksiyon çalıştırması (elle, arka planda ya da zamanlanmış) kalırsa veya hata verirse
      bu kanallara mesaj gider: hangi adım, hangi kural, gelen değer ve sonucun bağlantısı.
    </p>

    <form v-if="isAdmin" class="card form-card" data-testid="channel-form" @submit.prevent="create">
      <h2>Yeni kanal</h2>
      <div class="form-grid">
        <label>
          Ad
          <input v-model="form.name" required maxlength="100" placeholder="QA ekibi" data-testid="channel-name" />
        </label>
        <label>
          Tip
          <select v-model="form.type" data-testid="channel-type">
            <option v-for="(t, key) in TYPES" :key="key" :value="key">{{ t.label }}</option>
          </select>
        </label>
        <label>
          Ne zaman?
          <select v-model="form.notify_on">
            <option value="failure">Sadece başarısız olunca</option>
            <option value="always">Her çalıştırmada</option>
          </select>
        </label>
      </div>
      <label>
        {{ form.type === 'email' ? 'E-posta adres(ler)i' : 'Webhook adresi' }}
        <input
          v-model="form.target"
          required
          class="mono"
          :placeholder="TYPES[form.type].placeholder"
          data-testid="channel-target"
        />
      </label>
      <p v-if="form.type === 'email'" class="muted small-text">
        E-posta için sunucu ayarları <code>.env</code> dosyasında (SMTP_HOST, SMTP_PORT, SMTP_USER…).
      </p>
      <p v-else class="muted small-text">
        Adres şifreli saklanır ve listede gizlenir. Denemek için ücretsiz bir adres:
        <a href="https://webhook.site" target="_blank" rel="noopener" class="link">webhook.site</a>
      </p>
      <p v-if="formError" class="form-error">{{ formError }}</p>
      <button type="submit" :disabled="saving" data-testid="channel-submit">
        {{ saving ? 'Ekleniyor…' : 'Kanal ekle' }}
      </button>
    </form>
    <p v-else class="muted">Kanalları sadece Admin ekleyip düzenleyebilir.</p>

    <p v-if="notice" class="form-notice">{{ notice }}</p>
    <p v-if="error" class="form-error">{{ error }}</p>

    <div class="card table-card">
      <table class="table" data-testid="channel-table">
        <thead>
          <tr>
            <th>Ad</th>
            <th>Tip</th>
            <th>Hedef</th>
            <th>Ne zaman</th>
            <th>Son gönderim</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in channels" :key="c.id" :class="{ 'row-inactive': !c.enabled }">
            <td>{{ c.name }}</td>
            <td>{{ TYPES[c.type]?.label ?? c.type }}</td>
            <td><code class="break">{{ c.target_preview }}</code></td>
            <td class="muted">{{ c.notify_on === 'always' ? 'Her zaman' : 'Başarısızsa' }}</td>
            <td>
              <span
                v-if="c.last_status"
                class="badge"
                :class="c.last_status === 'ok' ? 'badge--active' : 'badge--inactive'"
                :title="c.last_error ?? ''"
              >
                {{ c.last_status === 'ok' ? 'Başarılı' : 'Hata' }}
              </span>
              <span class="muted small-text"> {{ formatTime(c.last_sent_at) }}</span>
              <div v-if="c.last_error" class="form-error small-text">{{ c.last_error }}</div>
            </td>
            <td class="actions">
              <template v-if="isAdmin">
                <button class="btn-small btn-secondary" :data-testid="`channel-test-${c.id}`" @click="sendTest(c)">
                  Deneme gönder
                </button>
                <button class="btn-small btn-secondary" @click="update(c, { enabled: !c.enabled })">
                  {{ c.enabled ? 'Durdur' : 'Etkinleştir' }}
                </button>
                <button class="btn-small btn-danger" @click="remove(c)">Sil</button>
              </template>
            </td>
          </tr>
          <tr v-if="!loading && channels.length === 0">
            <td colspan="6" class="muted">Henüz kanal yok.</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
