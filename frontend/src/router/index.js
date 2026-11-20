import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '@/views/HomeView.vue'

// Yeni sayfalar buraya eklenir. İleride (ATOP-21) rol bazlı "meta.roles" ile korunacak.
const routes = [
  { path: '/', name: 'home', component: HomeView, meta: { title: 'Genel Bakış' } },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/NotFoundView.vue'),
    meta: { title: 'Sayfa bulunamadı' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.afterEach((to) => {
  document.title = `${to.meta.title ?? ''} · API Test Platformu`
})

export default router
