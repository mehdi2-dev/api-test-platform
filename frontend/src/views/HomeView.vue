<script setup>
import { onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useSystemStore } from '@/stores/system'

const system = useSystemStore()
const { health, loading, error, checkedAt, isHealthy } = storeToRefs(system)

const labels = { database: 'PostgreSQL', redis: 'Redis' }

onMounted(() => system.fetchHealth())
</script>

<template>
  <section>
    <header class="page-header">
      <h1>Genel Bakış</h1>
      <button :disabled="loading" @click="system.fetchHealth()">
        {{ loading ? 'Kontrol ediliyor…' : 'Yenile' }}
      </button>
    </header>

    <div v-if="error" class="card card--error">
      <strong>{{ error }}</strong>
      <p>Backend'in <code>http://localhost:8000</code> adresinde çalıştığından emin olun.</p>
    </div>

    <div v-else-if="health" class="card">
      <div class="status-line">
        <span class="dot" :class="isHealthy ? 'dot--ok' : 'dot--error'" />
        <strong>{{ isHealthy ? 'Tüm sistemler çalışıyor' : 'Bazı servisler yanıt vermiyor' }}</strong>
      </div>
      <p class="muted">{{ health.app }} · ortam: {{ health.environment }}</p>

      <ul class="checks">
        <li v-for="(value, key) in health.checks" :key="key">
          <span class="dot" :class="value === 'ok' ? 'dot--ok' : 'dot--error'" />
          {{ labels[key] ?? key }}
          <span class="muted">{{ value === 'ok' ? 'bağlı' : 'hata' }}</span>
        </li>
      </ul>
    </div>

    <p v-if="checkedAt" class="muted small">
      Son kontrol: {{ checkedAt.toLocaleTimeString('tr-TR') }}
    </p>
  </section>
</template>
