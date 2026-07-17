import { createRouter, createWebHistory } from 'vue-router'

import { loadSession, session } from './auth/session'
import LoginView from './views/LoginView.vue'
import MeetingsView from './views/MeetingsView.vue'
import RegisterView from './views/RegisterView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: LoginView, meta: { public: true } },
    { path: '/register', component: RegisterView, meta: { public: true } },
    { path: '/', component: MeetingsView },
    { path: '/meetings/:id', component: () => import('./views/MeetingDetailView.vue') },
    { path: '/actions', component: () => import('./views/OpenActionsView.vue') },
    { path: '/account', component: () => import('./views/AccountView.vue') },
    { path: '/admin/users', component: () => import('./views/AdminUsersView.vue'), meta: { admin: true } },
    { path: '/admin/plugins', component: () => import('./views/AdminPluginsView.vue'), meta: { admin: true } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach(async (to) => {
  if (!session.loaded) await loadSession()
  if (!to.meta.public && !session.user) return '/login'
  if (to.meta.public && session.user) return '/'
  if (to.meta.admin && session.user?.role !== 'admin') return '/'
})

export default router
