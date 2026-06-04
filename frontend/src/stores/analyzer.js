import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchRepos, analyzeApi, analyzeJira, saveAnalysisFeedback } from '../api'

export const useAnalyzerStore = defineStore('analyzer', () => {
  const repos = ref([])
  const result = ref(null)
  const jiraResult = ref(null)
  const lastJiraRequest = ref(null)
  const feedback = ref(null)
  const loading = ref(false)
  const error = ref(null)

  async function loadRepos() {
    try {
      const res = await fetchRepos()
      repos.value = res.data.repos || []
    } catch (e) {
      error.value = '加载仓库列表失败: ' + (e.message || '未知错误')
    }
  }

  async function analyze(params) {
    loading.value = true
    error.value = null
    result.value = null

    try {
      const res = await analyzeApi(params)
      result.value = res.data
    } catch (e) {
      error.value = e.response?.data?.detail || e.message || '分析失败'
    } finally {
      loading.value = false
    }
  }

  async function analyzeJiraIssue(params) {
    loading.value = true
    error.value = null
    jiraResult.value = null
    feedback.value = null
    lastJiraRequest.value = params

    try {
      const res = await analyzeJira(params)
      jiraResult.value = res.data
    } catch (e) {
      error.value = e.response?.data?.detail || e.message || 'JIRA 分析失败'
    } finally {
      loading.value = false
    }
  }

  async function saveFeedback(payload) {
    const request = {
      issue_key: jiraResult.value?.jira?.key || jiraResult.value?.issue_key,
      jira_url: jiraResult.value?.jira_url || lastJiraRequest.value?.jira_url,
      predicted_causes: (jiraResult.value?.analysis?.possible_causes || []).slice(0, 3),
      ...payload
    }

    try {
      const res = await saveAnalysisFeedback(request)
      feedback.value = {
        ...request,
        saved_at: res.data.saved_at
      }
    } catch (e) {
      error.value = e.response?.data?.detail || e.message || '保存反馈失败'
      feedback.value = {
        ...request,
        saved_at: new Date().toLocaleString(),
        local_only: true
      }
    }
  }

  return {
    repos,
    result,
    jiraResult,
    lastJiraRequest,
    feedback,
    loading,
    error,
    loadRepos,
    analyze,
    analyzeJiraIssue,
    saveFeedback
  }
})
