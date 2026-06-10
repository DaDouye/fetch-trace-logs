import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'

const http = axios.create({
  baseURL: '/api',
  timeout: 300000,
  headers: {
    'Content-Type': 'application/json'
  }
})

export const useTraceStore = defineStore('trace', () => {
  const sqlList = ref([])
  const loading = ref(false)
  const error = ref(null)
  const traceId = ref(null)

  async function analyzeTrace(traceIdInput, cookies) {
    loading.value = true
    error.value = null
    sqlList.value = []
    traceId.value = traceIdInput

    try {
      const res = await http.post('/analyze-trace', {
        trace_id: traceIdInput,
        cookies: cookies
      })
      sqlList.value = res.data.sql_list || []
      if (res.data.error) {
        error.value = res.data.error
      }
    } catch (e) {
      error.value = e.response?.data?.detail || e.message || '分析失败'
    } finally {
      loading.value = false
    }
  }

  return {
    sqlList,
    loading,
    error,
    traceId,
    analyzeTrace
  }
})
