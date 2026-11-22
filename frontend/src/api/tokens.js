// Token'lar tarayıcının localStorage'ında tutulur; sayfa yenilense de oturum kapanmaz.
// Not: localStorage XSS saldırılarına açıktır; üretimde httpOnly cookie daha güvenli bir seçenektir.

const ACCESS_KEY = 'atp_access_token'
const REFRESH_KEY = 'atp_refresh_token'

export const tokens = {
  get access() {
    return localStorage.getItem(ACCESS_KEY)
  },
  get refresh() {
    return localStorage.getItem(REFRESH_KEY)
  },
  set(pair) {
    localStorage.setItem(ACCESS_KEY, pair.access_token)
    localStorage.setItem(REFRESH_KEY, pair.refresh_token)
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
  },
}
