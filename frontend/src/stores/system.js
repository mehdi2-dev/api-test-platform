import { defineStore } from 'pinia'
import api from '@/api/client'

export const useSystemStore = defineStore('system', {
  state: () => ({
    health: null,
    loading: false,
    error: null,
    checkedAt: null,
  }),

  getters: {
    isHealthy: (state) => state.health?.status === 'ok',
  },

  actions: {
    async fetchHealth() {
      this.loading = true
      this.error = null
      try {
        const { data } = await api.get('/health')
        this.health = data
      } catch (err) {
        // 503 durumunda da gövde gelir; bağımlılıkların durumunu göstermek için kullan
        if (err.response?.data?.checks) {
          this.health = err.response.data
        } else {
          this.health = null
          this.error = 'Backend\'e ulaşılamıyor'
        }
      } finally {
        this.loading = false
        this.checkedAt = new Date()
      }
    },
  },
})
