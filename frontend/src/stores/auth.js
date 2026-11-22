import { defineStore } from 'pinia'
import api from '@/api/client'
import { tokens } from '@/api/tokens'

export const ROLE_LABELS = { admin: 'Admin', tester: 'Tester', viewer: 'Viewer' }

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null,
    // Sayfa açılışında "kim giriş yapmış?" sorusu bir kez soruldu mu?
    loaded: false,
  }),

  getters: {
    isLoggedIn: (state) => state.user !== null,
    role: (state) => state.user?.role ?? null,
  },

  actions: {
    hasRole(...roles) {
      return this.user !== null && roles.includes(this.user.role)
    },

    async login(email, password) {
      const { data } = await api.post('/auth/login', { email, password })
      tokens.set(data)
      await this.fetchMe()
    },

    async fetchMe() {
      if (!tokens.access) {
        this.user = null
        this.loaded = true
        return null
      }
      try {
        const { data } = await api.get('/auth/me')
        this.user = data
      } catch {
        this.user = null
      } finally {
        this.loaded = true
      }
      return this.user
    },

    logout() {
      tokens.clear()
      this.user = null
    },
  },
})
