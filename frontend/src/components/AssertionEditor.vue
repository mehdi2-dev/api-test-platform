<script setup>
// Kod yazmadan test kuralı (assertion) ekleme formu (ATOP-36).
// v-model ile [{ type, target, operator, expected, enabled }] listesi bağlanır.
const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  readonly: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

const TYPES = [
  { value: 'status_code', label: 'Durum kodu' },
  { value: 'response_time', label: 'Yanıt süresi' },
  { value: 'json_path', label: 'JSON alanı' },
  { value: 'header', label: 'Header' },
]

const OPERATORS = {
  status_code: [
    { value: 'equals', label: 'eşittir' },
    { value: 'not_equals', label: 'eşit değildir' },
    { value: 'in_range', label: 'aralıkta (2xx, 200-299)' },
    { value: 'in_list', label: 'listede (200,201)' },
  ],
  response_time: [{ value: 'less_than', label: 'şundan kısa (ms)' }],
  json_path: [
    { value: 'exists', label: 'var' },
    { value: 'not_exists', label: 'yok' },
    { value: 'equals', label: 'eşittir' },
    { value: 'not_equals', label: 'eşit değildir' },
    { value: 'contains', label: 'içerir' },
    { value: 'matches', label: 'regex ile eşleşir' },
    { value: 'type_is', label: 'tipi' },
    { value: 'greater_than', label: 'büyüktür' },
    { value: 'less_than', label: 'küçüktür' },
  ],
  header: [
    { value: 'exists', label: 'var' },
    { value: 'not_exists', label: 'yok' },
    { value: 'equals', label: 'eşittir' },
    { value: 'contains', label: 'içerir' },
  ],
}

const JSON_TYPES = ['string', 'number', 'boolean', 'object', 'array', 'null']
const NO_EXPECTED = ['exists', 'not_exists']

const PLACEHOLDERS = {
  status_code: { equals: '200', not_equals: '500', in_range: '2xx', in_list: '200,201,204' },
  response_time: { less_than: '1000' },
}

const hasTarget = (row) => row.type === 'json_path' || row.type === 'header'
const hasExpected = (row) => !NO_EXPECTED.includes(row.operator)

function expectedPlaceholder(row) {
  if (row.type === 'json_path') {
    if (row.operator === 'matches') return '^\\d+$'
    if (['greater_than', 'less_than'].includes(row.operator)) return '10'
    return 'ok'
  }
  if (row.type === 'header') return 'application/json'
  return PLACEHOLDERS[row.type]?.[row.operator] ?? ''
}

function emitRows(rows) {
  emit('update:modelValue', rows)
}

function update(index, changes) {
  emitRows(props.modelValue.map((row, i) => (i === index ? { ...row, ...changes } : row)))
}

function changeType(index, type) {
  // Tip değişince o tipe uygun ilk operatörü seç ve hedefi temizle
  update(index, {
    type,
    operator: OPERATORS[type][0].value,
    target: type === 'json_path' ? '$.' : '',
    expected: '',
  })
}

function add(rule) {
  emitRows([...props.modelValue, { target: '', expected: '', enabled: true, ...rule }])
}

function remove(index) {
  emitRows(props.modelValue.filter((_, i) => i !== index))
}
</script>

<template>
  <div class="assertions" data-testid="assertions">
    <p class="muted hint">
      Her çalıştırmada cevap bu kurallarla kontrol edilir. Hepsi geçerse test <b>Geçti</b>, biri
      bile kalırsa <b>Kaldı</b> olur. JSON alanları için yol örnekleri:
      <code>$.status</code>, <code>$.data.user.id</code>, <code>$.items[0].name</code>
    </p>

    <div v-for="(row, i) in modelValue" :key="i" class="assertion-row" :data-testid="`rule-${i}`">
      <input
        type="checkbox"
        :checked="row.enabled"
        :disabled="readonly"
        title="Kural etkin mi?"
        @change="update(i, { enabled: $event.target.checked })"
      />
      <select
        :value="row.type"
        :disabled="readonly"
        :data-testid="`rule-type-${i}`"
        @change="changeType(i, $event.target.value)"
      >
        <option v-for="t in TYPES" :key="t.value" :value="t.value">{{ t.label }}</option>
      </select>

      <input
        v-if="hasTarget(row)"
        :value="row.target"
        :readonly="readonly"
        :placeholder="row.type === 'json_path' ? '$.status' : 'Content-Type'"
        class="mono"
        :data-testid="`rule-target-${i}`"
        @input="update(i, { target: $event.target.value })"
      />
      <span v-else class="assertion-gap"></span>

      <select
        :value="row.operator"
        :disabled="readonly"
        :data-testid="`rule-operator-${i}`"
        @change="update(i, { operator: $event.target.value })"
      >
        <option v-for="o in OPERATORS[row.type]" :key="o.value" :value="o.value">
          {{ o.label }}
        </option>
      </select>

      <template v-if="hasExpected(row)">
        <select
          v-if="row.operator === 'type_is'"
          :value="row.expected"
          :disabled="readonly"
          @change="update(i, { expected: $event.target.value })"
        >
          <option value="" disabled>tip seçin</option>
          <option v-for="t in JSON_TYPES" :key="t" :value="t">{{ t }}</option>
        </select>
        <input
          v-else
          :value="row.expected"
          :readonly="readonly"
          :placeholder="expectedPlaceholder(row)"
          class="mono"
          :data-testid="`rule-expected-${i}`"
          @input="update(i, { expected: $event.target.value })"
        />
      </template>
      <span v-else class="assertion-gap"></span>

      <button
        v-if="!readonly"
        type="button"
        class="btn-small btn-secondary"
        title="Kuralı sil"
        @click="remove(i)"
      >
        ✕
      </button>
    </div>

    <p v-if="modelValue.length === 0" class="muted kv-empty">Henüz kural yok.</p>

    <div v-if="!readonly" class="assertion-presets">
      <button
        type="button"
        class="btn-small btn-secondary"
        data-testid="add-status"
        @click="add({ type: 'status_code', operator: 'equals', expected: '200' })"
      >
        + Durum kodu 200
      </button>
      <button
        type="button"
        class="btn-small btn-secondary"
        data-testid="add-time"
        @click="add({ type: 'response_time', operator: 'less_than', expected: '1000' })"
      >
        + Süre &lt; 1000 ms
      </button>
      <button
        type="button"
        class="btn-small btn-secondary"
        data-testid="add-json"
        @click="add({ type: 'json_path', target: '$.', operator: 'exists' })"
      >
        + JSON alanı
      </button>
      <button
        type="button"
        class="btn-small btn-secondary"
        @click="add({ type: 'header', target: 'Content-Type', operator: 'contains', expected: 'json' })"
      >
        + Header
      </button>
    </div>
  </div>
</template>
