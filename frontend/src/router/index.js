import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'Home',
    component: () => import('@/views/HomeView.vue')
  },
  {
    path: '/inspect',
    name: 'Inspect',
    component: () => import('@/views/InspectView.vue')
  },
  {
    path: '/pipes-counting',
    name: 'PipesCounting',
    component: () => import('@/views/PipesCountingView.vue')
  },
  {
    path: '/dataset',
    name: 'Dataset',
    component: () => import('@/views/DatasetView.vue')
  },
  {
    path: '/knowledge-graph',
    name: 'KnowledgeGraph',
    component: () => import('@/views/KnowledgeGraphView.vue')
  },
  {
    path: '/regulations',
    name: 'RegulationKnowledge',
    component: () => import('@/views/RegulationKnowledgeView.vue')
  },
  {
    path: '/multimodal-search',
    name: 'MultimodalSearch',
    component: () => import('@/views/MultimodalSearchView.vue')
  },
  {
    path: '/history',
    name: 'History',
    component: () => import('@/views/HistoryView.vue')
  },
  {
    path: '/monitor',
    name: 'Monitor',
    component: () => import('@/views/MonitorView.vue')
  },
  {
    path: '/about',
    name: 'About',
    component: () => import('@/views/AboutView.vue')
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
