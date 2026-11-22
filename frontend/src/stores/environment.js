import { defineStore } from 'pinia'
import api from '@/api/client'

// Seçili ortam tarayıcıda hatırlanır; sayfa yenilense de aynı ortam seçili kalır
const STORAGE_KEY = 'atp_active_environment'

function readActive() {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return value ? Number(value) : null
  } catch {
    return null
  }
}

export const useEnvironmentStore = defineStore('environment', {
  state: () => ({
    items: [],
    activeId: readActive(),
    loaded: false,
  }),

  getters: {
    active: (state) => state.items.find((env) => env.id === state.activeId) ?? null,
  },

  actions: {
    async load() {
      const { data } = await api.get('/environments')
      this.items = data
      this.loaded = true
      // Seçili ortam silinmişse seçimi kaldır
      if (this.activeId !== null && !this.active) this.setActive(null)
    },

    setActive(id) {
      this.activeId = id
      try {
        if (id === null) localStorage.removeItem(STORAGE_KEY)
        else localStorage.setItem(STORAGE_KEY, String(id))
      } catch {
        // Tarayıcı depolaması kapalıysa seçim sadece bu sekmede geçerli olur
      }
    },

    reset() {
      this.items = []
      this.loaded = false
    },
  },
})
