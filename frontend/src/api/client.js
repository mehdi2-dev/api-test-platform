import axios from 'axios'

// Tüm backend istekleri bu istemciden geçer.
// İleride (ATOP-21) JWT token'ı buradaki interceptor ile eklenecek.
const api = axios.create({
  baseURL: '/api',
  timeout: 10000,
})

export default api
