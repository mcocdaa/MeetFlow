import { createRouter, createWebHistory } from 'vue-router'

import { loadSession, session } from './auth/session'
import LoginView from './views/LoginView.vue'
import RegisterView from './views/RegisterView.vue'
import HomeView from './views/HomeView.vue'
import ProjectsView from './views/ProjectsView.vue'
import WorkspacePlaceholderView from './views/WorkspacePlaceholderView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: LoginView, meta: { public: true } },
    { path: '/register', component: RegisterView, meta: { public: true } },
    { path: '/', component: HomeView },
    { path: '/projects', component: ProjectsView },
    { path: '/projects/:id', component: WorkspacePlaceholderView },
    { path: '/meetings', component: () => import('./views/MeetingsView.vue') },
    { path: '/meetings/:id', component: () => import('./views/MeetingDetailView.vue') },
    { path: '/actions', component: WorkspacePlaceholderView },
    { path: '/decisions', component: WorkspacePlaceholderView },
    { path: '/inbox', component: WorkspacePlaceholderView },
    { path: '/ai-tasks', component: WorkspacePlaceholderView },
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
