import { createRouter, createWebHistory } from 'vue-router'
import JiraAnalysisPage from '../pages/JiraAnalysisPage.vue'
import TraceAnalysisPage from '../pages/TraceAnalysisPage.vue'

const routes = [
  {
    path: '/',
    redirect: '/jira-analysis'
  },
  {
    path: '/trace-analysis',
    name: 'TraceAnalysis',
    component: TraceAnalysisPage
  },
  {
    path: '/jira-analysis',
    name: 'JiraAnalysis',
    component: JiraAnalysisPage
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
