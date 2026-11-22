import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import { setUnauthorizedHandler } from './api/client'
import { useAuthStore } from './stores/auth'
import './style.css'

const app = createApp(App)
app.use(createPinia())

// Oturum tamamen düşerse (token ve refresh geçersiz) giriş sayfasına gönder
setUnauthorizedHandler(() => {
  useAuthStore().user = null
  const current = router.currentRoute.value
  if (current.name !== 'login') {
    router.push({ name: 'login', query: { redirect: current.fullPath } })
  }
})

app.use(router)
app.mount('#app')
