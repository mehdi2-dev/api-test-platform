// İki metni satır satır karşılaştırır (hata raporundaki "önceki başarılı cevap" karşılaştırması).
// Sonuç: [{ type: 'same' | 'added' | 'removed', text }]
// En uzun ortak alt dizi (LCS) yöntemi; çok uzun metinlerde ilk MAX_LINES satıra bakılır.

const MAX_LINES = 400

export function lineDiff(before, after) {
  const a = (before ?? '').split('\n').slice(0, MAX_LINES)
  const b = (after ?? '').split('\n').slice(0, MAX_LINES)

  // lcs[i][j]: a[i..] ile b[j..] arasındaki en uzun ortak satır sayısı
  const lcs = Array.from({ length: a.length + 1 }, () => new Array(b.length + 1).fill(0))
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      lcs[i][j] = a[i] === b[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1])
    }
  }

  const result = []
  let i = 0
  let j = 0
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      result.push({ type: 'same', text: a[i] })
      i++
      j++
    } else if (lcs[i + 1][j] >= lcs[i][j + 1]) {
      result.push({ type: 'removed', text: a[i++] })
    } else {
      result.push({ type: 'added', text: b[j++] })
    }
  }
  while (i < a.length) result.push({ type: 'removed', text: a[i++] })
  while (j < b.length) result.push({ type: 'added', text: b[j++] })
  return result
}

// JSON ise okunaklı biçimlendir, değilse olduğu gibi bırak
export function prettyJson(text) {
  if (!text || !text.trim()) return ''
  try {
    return JSON.stringify(JSON.parse(text), null, 2)
  } catch {
    return text
  }
}
