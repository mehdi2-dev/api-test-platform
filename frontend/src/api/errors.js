// Backend'in hata cevabını okunur bir metne çevirir.
// detail tek bir metin olabilir ya da FastAPI'nin doğrulama listesi olabilir.
export function errorMessage(err, fallback = 'Bir hata oluştu') {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string') return detail
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
