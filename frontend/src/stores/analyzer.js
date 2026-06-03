import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchRepos, analyzeApi, analyzeJira } from '../api'

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
      error.value = e.response?.data?.detail?.message || e.response?.data?.detail || e.message || '分析失败'
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
      error.value = e.response?.data?.detail?.message || e.response?.data?.detail || e.message || 'JIRA 分析失败'
    } finally {
      loading.value = false
    }
  }

  function saveFeedback(payload) {
    feedback.value = {
      ...payload,
      saved_at: new Date().toLocaleString()
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
