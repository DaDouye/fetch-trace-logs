import axios from 'axios'

const http = axios.create({
  baseURL: '/api',
  timeout: 30000,
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