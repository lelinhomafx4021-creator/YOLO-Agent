import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'overview', component: () => import('../pages/OverviewPage.vue') },
  { path: '/projects', name: 'projects', component: () => import('../pages/ProjectsPage.vue') },
  { path: '/projects/:id', name: 'project-detail', component: () => import('../pages/ProjectDetailPage.vue') },
  { path: '/training/:id', name: 'training-detail', component: () => import('../pages/TrainingRunDetailPage.vue') },
  { path: '/evaluations/:id', name: 'evaluation-detail', component: () => import('../pages/EvaluationDetailPage.vue') },
  { path: '/dataset/:id', name: 'dataset-preview', component: () => import('../pages/DatasetPreviewPage.vue') },
  { path: '/datasets', name: 'datasets', component: () => import('../pages/DatasetsPage.vue') },
  { path: '/datasets/workspace/:name', name: 'workspace-detail', component: () => import('../pages/WorkspaceDetailPage.vue') },
  { path: '/annotation', name: 'annotation', component: () => import('../pages/AnnotationStudioPage.vue') },
  { path: '/audit', name: 'audit', component: () => import('../pages/LabelAuditPage.vue') },
  { path: '/training', name: 'training', component: () => import('../pages/TrainingRunsPage.vue') },
  { path: '/registry', name: 'registry', component: () => import('../pages/ModelRegistryPage.vue') },
  { path: '/report', name: 'report', component: () => import('../pages/AiReportPage.vue') },
  { path: '/agent', name: 'agent', component: () => import('../pages/AgentChatPage.vue') },
  { path: '/inference', name: 'inference', component: () => import('../pages/InferencePage.vue') },
  { path: '/settings', name: 'settings', component: () => import('../pages/SettingsPage.vue') },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
