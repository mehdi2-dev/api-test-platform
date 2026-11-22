<script setup>
// Header ve query parametreleri için anahtar / değer satırları.
// v-model ile [{ key, value, enabled }] listesi bağlanır.
const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  keyPlaceholder: { type: String, default: 'Anahtar' },
  valuePlaceholder: { type: String, default: 'Değer' },
  readonly: { type: Boolean, default: false },
  testid: { type: String, default: 'kv' },
})
const emit = defineEmits(['update:modelValue'])

function update(index, field, value) {
  emit(
    'update:modelValue',
    props.modelValue.map((row, i) => (i === index ? { ...row, [field]: value } : row)),
  )
}

function addRow() {
  emit('update:modelValue', [...props.modelValue, { key: '', value: '', enabled: true }])
}

function removeRow(index) {
  emit(
    'update:modelValue',
    props.modelValue.filter((_, i) => i !== index),
  )
}
</script>

<template>
  <div class="kv" :data-testid="testid">
    <div v-for="(row, i) in modelValue" :key="i" class="kv-row">
      <input
        type="checkbox"
        :checked="row.enabled"
        :disabled="readonly"
        title="Gönderilsin mi?"
        @change="update(i, 'enabled', $event.target.checked)"
      />
      <input
        :value="row.key"
        :placeholder="keyPlaceholder"
        :readonly="readonly"
        :data-testid="`${testid}-key-${i}`"
        @input="update(i, 'key', $event.target.value)"
      />
      <input
        :value="row.value"
        :placeholder="valuePlaceholder"
        :readonly="readonly"
        :data-testid="`${testid}-value-${i}`"
        @input="update(i, 'value', $event.target.value)"
      />
      <button
        v-if="!readonly"
        type="button"
        class="btn-small btn-secondary"
        title="Satırı sil"
        @click="removeRow(i)"
      >
        ✕
      </button>
    </div>
    <p v-if="modelValue.length === 0" class="muted kv-empty">Satır yok</p>
    <button
      v-if="!readonly"
      type="button"
      class="btn-small btn-secondary"
      :data-testid="`${testid}-add`"
      @click="addRow"
    >
      + Satır ekle
    </button>
  </div>
</template>
