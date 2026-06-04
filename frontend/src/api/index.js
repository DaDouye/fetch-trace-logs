import axios from 'axios'

const http = axios.create({
  baseURL: '/api',
  timeout: 300000,  // 5分钟
  headers: {
    'Content-Type': 'application/json'
  }
})

export function fetchRepos() {
  return http.get('/repos')
}

export function analyzeApi(params) {
  return http.post('/analyze', params)
}

export function analyzeJira(params) {
  return http.post('/analyze-jira', params)
}

export function saveAnalysisFeedback(params) {
  return http.post('/analysis-feedback', params)
}
