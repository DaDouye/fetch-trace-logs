import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchRepos, analyzeApi } from '../api'

export const useAnalyzerStore = defineStore('analyzer', () => {
  const repos = ref([])
  const result = ref(null)
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

  return { repos, result, loading, error, loadRepos, analyze }
})