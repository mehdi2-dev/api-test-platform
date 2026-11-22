import axios from 'axios'
import { tokens } from './tokens'

// Tüm backend istekleri bu istemciden geçer.
const api = axios.create({
  baseURL: '/api',
  timeout: 10000,
})

// Oturum tamamen düştüğünde (refresh de başarısızsa) ne yapılacağını main.js belirler
let onUnauthorized = () => {}
export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler
}

// 1) Her isteğe, varsa access token'ı ekle
api.interceptors.request.use((config) => {
  if (tokens.access) {
    config.headers.Authorization = `Bearer ${tokens.access}`
  }
  return config
})

// 2) 401 gelirse bir kez refresh token ile yeni token al ve isteği tekrarla.
//    Aynı anda birden çok istek 401 alırsa hepsi tek bir refresh'i bekler.
let refreshing = null

function refreshTokens() {
  if (!tokens.refresh) return Promise.resolve(false)
  if (!refreshing) {
    refreshing = axios
      .post('/api/auth/refresh', { refresh_token: tokens.refresh })
      .then(({ data }) => {
        tokens.set(data)
        return true
      })
      .catch(() => false)
      .finally(() => {
        refreshing = null
      })
  }
  return refreshing
}

const AUTH_URLS = ['/auth/login', '/auth/refresh']

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const { config, response } = error
    const isAuthCall = AUTH_URLS.some((url) => config?.url?.startsWith(url))

    if (response?.status === 401 && config && !config._retried && !isAuthCall) {
      config._retried = true
      if (await refreshTokens()) {
        return api(config)
      }
      tokens.clear()
      onUnauthorized()
    }
    return Promise.reject(error)
  },
)

export default api
