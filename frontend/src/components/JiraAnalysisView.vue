<template>
  <div class="jira-analysis-view">
    <n-spin :show="loading">
      <template v-if="jiraResult">
        <n-card title="故障初筛卡片" embedded class="section-card">
          <div class="card-header">
            <div>
              <n-tag type="info">{{ jiraResult.jira?.key || jiraResult.issue_key }}</n-tag>
              <h2>{{ jiraResult.jira?.summary || '暂无摘要' }}</h2>
            </div>
            <n-space>
              <n-tag>{{ requestContext.environment || '未填写环境' }}</n-tag>
              <n-tag v-if="requestContext.problem_type" type="warning">{{ requestContext.problem_type }}</n-tag>
            </n-space>
          </div>

          <n-divider />

          <section class="card-section">
            <h3>可能原因 Top 3</h3>
            <template v-if="topCauses.length">
              <n-list>
                <n-list-item v-for="(cause, index) in topCauses" :key="index">
                  <div class="cause-block">
                    <div class="cause-title">
                      <n-tag type="warning" size="small">Top {{ index + 1 }}</n-tag>
                      <strong>{{ cause.category || '待判断原因' }}</strong>
                    </div>
                    <p v-if="cause.analysis">{{ cause.analysis }}</p>
                    <p v-if="cause.suggestion" class="muted-text">{{ cause.suggestion }}</p>
                    <template v-if="cause.evidence_files?.length">
                      <div class="evidence-box">
                        <span>证据</span>
                        <n-ul>
                          <n-li v-for="file in cause.evidence_files.slice(0, 3)" :key="file.file_path">
                            {{ getEvidenceTitle(file.file_path) }}
                          </n-li>
                        </n-ul>
                      </div>
                    </template>
                  </div>
                </n-list-item>
              </n-list>
            </template>
            <n-empty v-else description="暂未形成明确原因，请补充更多上下文" />
          </section>

          <section class="card-section">
            <h3>排查范围</h3>
            <n-descriptions label-placement="top" :column="3">
              <n-descriptions-item label="时间窗口">
                {{ timeWindowText }}
              </n-descriptions-item>
              <n-descriptions-item label="服务范围">
                <n-space v-if="requestContext.services?.length">
                  <n-tag v-for="service in requestContext.services" :key="service" size="small">
                    {{ service }}
                  </n-tag>
                </n-space>
                <span v-else>未填写</span>
              </n-descriptions-item>
              <n-descriptions-item label="Trace">
                <div>{{ displayTraceId }}</div>
                <div v-if="traceIdHint" class="muted-text">{{ traceIdHint }}</div>
              </n-descriptions-item>
            </n-descriptions>
          </section>

          <section class="card-section">
            <h3>影响信号</h3>
            <div class="signal-grid">
              <div class="signal-item">
                <span>相关线索</span>
                <strong>{{ evidenceCount }} 条</strong>
              </div>
              <div class="signal-item">
                <span>Trace SQL</span>
                <strong>{{ hasSqlText }}</strong>
              </div>
              <div class="signal-item">
                <span>可能原因</span>
                <strong>{{ topCauses.length }} 个</strong>
              </div>
            </div>
          </section>

          <section class="card-section">
            <h3>关键时间线</h3>
            <n-list>
              <n-list-item v-for="item in timelineItems" :key="item.label">
                <n-thing :title="item.label" :description="item.value" />
              </n-list-item>
            </n-list>
          </section>

          <section class="card-section">
            <h3>链路日志分析</h3>
            <template v-if="traceSummary">
              <n-alert
                :type="traceSummary.success ? 'success' : 'error'"
                :title="traceSummary.success ? 'Trace 获取成功' : 'Trace 获取失败'"
              >
                {{ traceSummary.success ? traceSummary.evidence_summary : traceFailureReason }}
              </n-alert>

              <template v-if="traceSummary.success">
                <div class="trace-grid">
                  <div class="signal-item">
                    <span>涉及服务</span>
                    <strong>{{ traceSummary.services?.length || 0 }} 个</strong>
                    <p>{{ serviceText }}</p>
                  </div>
                  <div class="signal-item">
                    <span>最慢节点</span>
                    <strong>{{ slowestNodeText }}</strong>
                    <p>{{ slowestNodeCost }}</p>
                  </div>
                  <div class="signal-item">
                    <span>异常节点</span>
                    <strong>{{ traceSummary.has_error ? '有' : '未识别到' }}</strong>
                    <p>{{ errorNodeText }}</p>
                  </div>
                  <div class="signal-item">
                    <span>SQL</span>
                    <div class="signal-title-row">
                      <strong>{{ traceSummary.has_sql ? `${traceSummary.sql_count || 0} 条` : '无' }}</strong>
                      <n-button
                        v-if="traceSqlList.length"
                        size="small"
                        type="primary"
                        secondary
                        @click="openSqlDetailPage"
                      >
                        查看详情
                      </n-button>
                    </div>
                    <p>{{ traceSummary.has_sql ? '已整理可读 SQL' : '链路中未发现 SQL' }}</p>
                  </div>
                </div>
              </template>
            </template>
            <n-empty v-else description="未提供 Trace ID，暂无链路日志分析" />
          </section>

          <section class="card-section">
            <h3>下一步建议</h3>
            <n-ul>
              <n-li v-for="item in nextActions" :key="item">{{ item }}</n-li>
            </n-ul>
          </section>

          <section class="card-section">
            <h3>信息缺口</h3>
            <n-ul>
              <n-li v-for="item in informationGaps" :key="item">{{ item }}</n-li>
            </n-ul>
          </section>
        </n-card>

        <n-card title="人工反馈" embedded class="section-card">
          <n-form label-placement="top">
            <n-grid :cols="2" :x-gap="16" responsive="screen" item-responsive>
              <n-gi span="1">
                <n-form-item label="这张卡片是否有帮助">
                  <n-select
                    v-model:value="feedbackForm.helpful"
                    :options="yesNoOptions"
                    placeholder="请选择"
                  />
                </n-form-item>
              </n-gi>
              <n-gi span="1">
                <n-form-item label="是否命中最终根因">
                  <n-select
                    v-model:value="feedbackForm.hitRootCause"
                    :options="yesNoOptions"
                    placeholder="请选择"
                  />
                </n-form-item>
              </n-gi>
            </n-grid>
            <n-form-item label="实际根因">
              <n-input
                v-model:value="feedbackForm.rootCause"
                placeholder="人工确认后的真实原因"
              />
            </n-form-item>
            <n-form-item label="备注">
              <n-input
                v-model:value="feedbackForm.note"
                type="textarea"
                placeholder="补充这次卡片哪里有用、哪里不够"
                :autosize="{ minRows: 2, maxRows: 4 }"
              />
            </n-form-item>
            <n-space justify="end">
              <n-button type="primary" @click="saveFeedback">保存反馈</n-button>
            </n-space>
          </n-form>
          <n-alert v-if="savedFeedback" type="success" title="反馈已记录" style="margin-top: 16px">
            已记录本次人工判断：{{ savedFeedback.saved_at }}
          </n-alert>
        </n-card>
      </template>

      <n-empty v-else description="暂无初筛卡片" />
    </n-spin>
  </div>
</template>

<script setup>
import { computed, reactive } from 'vue'
import { useAnalyzerStore } from '../stores/analyzer'

const store = useAnalyzerStore()

const loading = computed(() => store.loading)
const jiraResult = computed(() => store.jiraResult)
const requestContext = computed(() => jiraResult.value?.request_context || store.lastJiraRequest || {})
const savedFeedback = computed(() => store.feedback)

const feedbackForm = reactive({
  helpful: null,
  hitRootCause: null,
  rootCause: '',
  note: ''
})

const yesNoOptions = [
  { label: '是', value: '是' },
  { label: '否', value: '否' },
  { label: '不确定', value: '不确定' }
]

const topCauses = computed(() =>
  (jiraResult.value?.analysis?.possible_causes || []).slice(0, 3)
)

const commentInsights = computed(() =>
  jiraResult.value?.analysis?.comment_insights || jiraResult.value?.jira?.comment_insights || null
)

const historicalCases = computed(() =>
  jiraResult.value?.analysis?.historical_cases || jiraResult.value?.historical_cases || []
)

const traceSummary = computed(() => jiraResult.value?.code_context?.trace_data || null)

const traceSqlList = computed(() => traceSummary.value?.sql || [])

const displayTraceId = computed(() =>
  traceSummary.value?.trace_id || requestContext.value.trace_id || '未提供'
)

const traceIdHint = computed(() => {
  const source = requestContext.value.trace_id_source
  if (source === 'manual') return '用户填写'
  if (source === 'jira') return requestContext.value.trace_id_note || '从 Jira 自动识别'
  return ''
})

const evidenceCount = computed(() => {
  const files = jiraResult.value?.code_context?.files?.length || 0
  const chains = jiraResult.value?.code_context?.call_chains?.length || 0
  const trace = jiraResult.value?.code_context?.trace_data ? 1 : 0
  return files + chains + trace
})

const hasSqlText = computed(() => {
  const trace = traceSummary.value
  if (!trace) return '未提供'
  return trace.has_sql ? '有' : '无'
})

const serviceText = computed(() => {
  const services = traceSummary.value?.services || []
  return services.length ? services.join('、') : '未识别到服务'
})

const slowestNodeText = computed(() => {
  const node = traceSummary.value?.slowest_node
  if (!node) return '未识别'
  return node.service_name || 'Unknown'
})

const slowestNodeCost = computed(() => {
  const node = traceSummary.value?.slowest_node
  if (!node) return '暂无耗时'
  return `${node.operation_name || 'Unknown'}，${node.duration_ms || 0}ms`
})

const errorNodeText = computed(() => {
  const nodes = traceSummary.value?.error_nodes || []
  if (!nodes.length) return '未发现明确异常标记'
  const node = nodes[0]
  return `${node.service_name || 'Unknown'}：${node.operation_name || 'Unknown'}`
})

const traceFailureReason = computed(() =>
  traceSummary.value?.failure_reason || traceSummary.value?.error || 'Trace 获取失败'
)

const timeWindowText = computed(() => {
  const window = requestContext.value.time_window
  if (!window?.start && !window?.end) return '未填写'
  return `${window.start || '未填写'} 至 ${window.end || '未填写'}`
})

const timelineItems = computed(() => {
  const jira = jiraResult.value?.jira || {}
  const items = [
    { label: '问题创建', value: formatDate(jira.created) || 'Jira 未返回创建时间' },
    { label: '排查窗口开始', value: requestContext.value.time_window?.start || '未填写' },
    { label: '排查窗口结束', value: requestContext.value.time_window?.end || '未填写' }
  ]

  if (jira.updated) {
    items.push({ label: '问题最近更新', value: formatDate(jira.updated) })
  }

  return items
})

const nextActions = computed(() => {
  const checklist = commentInsights.value?.diagnosis_checklist || []
  if (checklist.length) return checklist.slice(0, 3)

  const suggestions = topCauses.value
    .map(cause => cause.suggestion)
    .filter(Boolean)
    .slice(0, 3)

  if (suggestions.length) return suggestions

  return [
    '补充该时间窗口内的错误日志或 Trace ID',
    '确认服务范围是否覆盖真实请求链路',
    '对比问题发生前后的发布记录和关键指标变化'
  ]
})

const informationGaps = computed(() => {
  const gaps = []
  if (!requestContext.value.trace_id) gaps.push('缺少 Trace ID，链路证据可能不完整')
  if (!requestContext.value.extra_clues) gaps.push('缺少接口名或错误关键词，原因判断会偏粗')
  if (!jiraResult.value?.code_context?.trace_data) gaps.push('缺少链路追踪摘要')
  if (!jiraResult.value?.code_context?.files?.length) gaps.push('缺少相关证据文件或匹配线索')
  return gaps.length ? gaps : ['当前信息较完整，可由人工继续确认根因']
})

function formatDate(dateStr) {
  if (!dateStr) return ''
  return new Date(dateStr).toLocaleString()
}

function getEvidenceTitle(filePath) {
  if (!filePath) return '未命名证据'
  return filePath.split('/').pop()
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function openSqlDetailPage() {
  const sqlList = traceSqlList.value
  if (!sqlList.length) return

  const traceId = displayTraceId.value
  const title = `Trace SQL 详情 - ${traceId}`
  const rows = sqlList.map((item, index) => {
    const service = escapeHtml(item.service_name || 'Unknown')
    const duration = item.duration_ms ? `${escapeHtml(item.duration_ms)}ms` : '暂无耗时'
    const rid = item.rid ? escapeHtml(item.rid) : `SQL-${index + 1}`
    const sql = escapeHtml(item.sql || '未获取到 SQL 内容')
    return `
      <article class="sql-item">
        <div class="sql-meta">
          <span class="index">#${index + 1}</span>
          <span>${service}</span>
          <span>${duration}</span>
          <span>${rid}</span>
        </div>
        <pre>${sql}</pre>
      </article>
    `
  }).join('')

  const html = `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>${escapeHtml(title)}</title>
  <style>
    body {
      margin: 0;
      background: #f6f7f9;
      color: #1f2937;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    .page {
      max-width: 1180px;
      margin: 0 auto;
      padding: 24px;
    }
    .header {
      margin-bottom: 18px;
    }
    h1 {
      font-size: 22px;
      margin: 0 0 8px;
      font-weight: 650;
    }
    .summary {
      color: #667085;
      font-size: 14px;
    }
    .sql-item {
      background: #fff;
      border: 1px solid #e5e7eb;
      border-radius: 6px;
      padding: 14px;
      margin-bottom: 12px;
    }
    .sql-meta {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
      color: #667085;
      font-size: 12px;
      margin-bottom: 10px;
    }
    .index {
      color: #2563eb;
      font-weight: 650;
    }
    pre {
      margin: 0;
      padding: 12px;
      background: #101828;
      color: #f9fafb;
      border-radius: 6px;
      overflow-x: auto;
      white-space: pre-wrap;
      word-break: break-word;
      line-height: 1.6;
      font-size: 13px;
    }
  </style>
</head>
<body>
  <main class="page">
    <header class="header">
      <h1>${escapeHtml(title)}</h1>
      <div class="summary">共 ${sqlList.length} 条可读 SQL</div>
    </header>
    ${rows}
  </main>
</body>
</html>`

  const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const detailWindow = window.open(url, '_blank', 'noopener,noreferrer')
  if (!detailWindow) {
    URL.revokeObjectURL(url)
    return
  }
  setTimeout(() => URL.revokeObjectURL(url), 30000)
}

function saveFeedback() {
  store.saveFeedback({
    helpful: feedbackForm.helpful,
    hit_root_cause: feedbackForm.hitRootCause,
    root_cause: feedbackForm.rootCause,
    note: feedbackForm.note
  })
}
</script>

<style scoped>
.jira-analysis-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section-card {
  margin-bottom: 16px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.card-header h2 {
  font-size: 18px;
  line-height: 1.4;
  margin-top: 10px;
  font-weight: 600;
}

.card-section {
  margin-top: 18px;
}

.card-section h3 {
  font-size: 15px;
  margin-bottom: 10px;
  font-weight: 600;
}

.signal-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.trace-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-top: 12px;
}

.signal-item {
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 12px;
  background: #fafafa;
}

.signal-item span {
  display: block;
  color: #667085;
  font-size: 12px;
  margin-bottom: 6px;
}

.signal-item strong {
  font-size: 18px;
}

.signal-title-row {
  display: flex;
  gap: 10px;
  align-items: center;
  justify-content: space-between;
}

.signal-item p {
  margin-top: 8px;
  color: #667085;
  line-height: 1.5;
  word-break: break-word;
}

.cause-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.cause-title {
  display: flex;
  gap: 8px;
  align-items: center;
}

.muted-text {
  color: #667085;
  white-space: pre-wrap;
}

.evidence-box {
  border-left: 3px solid #d0d5dd;
  padding-left: 10px;
  color: #475467;
}

.evidence-box span {
  font-size: 12px;
  color: #667085;
}

.comment-box {
  margin-top: 12px;
}

.comment-box p {
  margin: 8px 0 0;
  line-height: 1.6;
  white-space: pre-wrap;
}

@media (max-width: 768px) {
  .card-header {
    flex-direction: column;
  }

  .signal-grid {
    grid-template-columns: 1fr;
  }

  .trace-grid {
    grid-template-columns: 1fr;
  }
}
</style>
