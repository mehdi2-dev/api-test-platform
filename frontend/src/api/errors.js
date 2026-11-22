// Backend'in hata cevabını okunur bir metne çevirir.
// detail tek bir metin, { code, message } nesnesi ya da FastAPI'nin doğrulama listesi olabilir.
export function errorMessage(err, fallback = 'Bir hata oluştu') {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object' && !Array.isArray(detail) && detail.message) {
    return detail.message
  }
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        const field = d.loc?.filter((part) => part !== 'body').join('.')
        const msg = (d.msg ?? '').replace(/^Value error, /, '')
        return field ? `${field}: ${msg}` : msg
      })
      .join(' · ')
  }
  if (!err?.response) return 'Sunucuya ulaşılamadı'
  return fallback
}

// Hata belirli bir koda sahip mi? (ör. 'production_confirmation_required')
export function errorCode(err) {
  const detail = err?.response?.data?.detail
  return detail && typeof detail === 'object' && !Array.isArray(detail) ? detail.code : null
}
