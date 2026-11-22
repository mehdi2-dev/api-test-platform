import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import HomeView from '@/views/HomeView.vue'

// meta.public: giriş yapmadan açılabilir
// meta.roles:  sadece bu rollerdeki kullanıcılar açabilir
// meta.layout: 'blank' ise sol menü gösterilmez
const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { title: 'Giriş', public: true, layout: 'blank' },
  },
  { path: '/', name: 'home', component: HomeView, meta: { title: 'Genel Bakış' } },
  {
    path: '/users',
    name: 'users',
    component: () => import('@/views/UsersView.vue'),
    meta: { title: 'Kullanıcılar', roles: ['admin'] },
  },
  {
    path: '/apis',
    name: 'apis',
    component: () => import('@/views/ApisView.vue'),
    meta: { title: "API'ler" },
  },
  {
    path: '/apis/new',
    name: 'api-new',
    component: () => import('@/views/ApiEditView.vue'),
    meta: { title: 'Yeni API', roles: ['admin', 'tester'] },
  },
  {
    path: '/apis/:id(\\d+)',
    name: 'api-edit',
    component: () => import('@/views/ApiEditView.vue'),
    meta: { title: 'API' },
  },
  {
    path: '/environments',
    name: 'environments',
    component: () => import('@/views/EnvironmentsView.vue'),
    meta: { title: 'Ortamlar' },
  },
  {
    path: '/403',
    name: 'forbidden',
    component: () => import('@/views/ForbiddenView.vue'),
    meta: { title: 'Yetkiniz yok' },
  },
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

// Her sayfa geçişinden önce: giriş yapılmış mı, rol yetiyor mu?
router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.loaded) {
    await auth.fetchMe()
  }

  if (to.meta.public) {
    // Giriş yapmış biri login sayfasına giderse ana sayfaya yönlendir
    return to.name === 'login' && auth.isLoggedIn ? { name: 'home' } : true
  }
  if (!auth.isLoggedIn) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.meta.roles && !auth.hasRole(...to.meta.roles)) {
    return { name: 'forbidden' }
  }
  return true
})

router.afterEach((to) => {
  document.title = `${to.meta.title ?? ''} · API Test Platformu`
})

export default router
