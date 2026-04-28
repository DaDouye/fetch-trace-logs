<template>
  <div class="jira-analysis-view">
    <n-spin :show="loading">
      <template v-if="jiraResult">
        <!-- JIRA Issue Section -->
        <n-card title="JIRA 问题" embedded class="section-card">
          <n-descriptions label-placement="top" :column="2">
            <n-descriptions-item label="问题编号">
              <n-tag type="info">{{ jiraResult.jira?.key }}</n-tag>
            </n-descriptions-item>
            <n-descriptions-item label="状态">
              <n-tag :type="getStatusType(jiraResult.jira?.status)">
                {{ jiraResult.jira?.status }}
              </n-tag>
            </n-descriptions-item>
            <n-descriptions-item label="问题类型">
              {{ jiraResult.jira?.issue_type }}
            </n-descriptions-item>
            <n-descriptions-item label="优先级">
              {{ jiraResult.jira?.priority }}
            </n-descriptions-item>
            <n-descriptions-item label="报告人">
              {{ jiraResult.jira?.reporter }}
            </n-descriptions-item>
            <n-descriptions-item label="负责人">
              {{ jiraResult.jira?.assignee || '未分配' }}
            </n-descriptions-item>
          </n-descriptions>

          <n-divider />
          <h4>摘要</h4>
          <p class="summary-text">{{ jiraResult.jira?.summary }}</p>

          <template v-if="jiraResult.jira?.description">
            <n-divider />
            <h4>描述</h4>
            <n-input
              type="textarea"
              :value="jiraResult.jira.description"
              read-only
              :autosize="{ minRows: 3, maxRows: 10 }"
            />
          </template>

          <template v-if="jiraResult.jira?.customfield_19900">
            <n-divider />
            <h4>线上问题描述字段</h4>
            <p class="summary-text">{{ jiraResult.jira.customfield_19900 }}</p>
          </template>

          <template v-if="jiraResult.jira?.attachment?.length">
            <n-divider />
            <h4>附件</h4>
            <n-list hoverable>
              <n-list-item v-for="(att, index) in jiraResult.jira.attachment" :key="index">
                <n-a :href="att.content" target="_blank">{{ att.filename }}</n-a>
              </n-list-item>
            </n-list>
          </template>
        </n-card>

        <!-- Possible Causes Section -->
        <n-card title="可能的原因" embedded class="section-card">
          <template v-if="jiraResult.analysis?.possible_causes?.length">
            <n-list>
              <n-list-item v-for="cause in jiraResult.analysis.possible_causes" :key="cause.id">
                <n-tag type="warning" size="small">{{ cause.category }}</n-tag>
                <p v-if="cause.analysis" class="cause-analysis">{{ cause.analysis }}</p>
                <p v-if="cause.suggestion" class="cause-suggestion">{{ cause.suggestion }}</p>
                <template v-if="cause.evidence_files?.length">
                  <n-divider />
                  <p class="evidence-label">相关代码文件:</p>
                  <n-ul>
                    <n-li v-for="file in cause.evidence_files" :key="file.file_path">
                      <n-text depth="3">{{ file.file_path }}</n-text>
                    </n-li>
                  </n-ul>
                </template>
              </n-list-item>
            </n-list>
          </template>
          <n-empty v-else description="未发现明显问题原因" />
        </n-card>

        <!-- Code Search Results -->
        <n-card
          v-if="jiraResult.code_context?.files?.length"
          title="相关代码文件"
          embedded
          class="section-card"
        >
          <n-list hoverable clickable>
            <n-list-item v-for="file in jiraResult.code_context.files" :key="file.file_path">
              <n-thing>
                <template #header>
                  {{ getFileName(file.file_path) }}
                </template>
                <template #description>
                  <n-text depth="3">{{ file.file_path }}</n-text>
                </template>
                <n-ul v-if="file.matches?.length">
                  <n-li v-for="(match, idx) in file.matches" :key="idx">
                    <n-text code>Line {{ match.line_number }}</n-text>
                    : {{ match.content.substring(0, 100) }}
                  </n-li>
                </n-ul>
              </n-thing>
            </n-list-item>
          </n-list>
        </n-card>

        <!-- Call Chain Section -->
        <n-card
          v-if="jiraResult.code_context?.call_chains?.length"
          title="调用链分析"
          embedded
          class="section-card"
        >
          <n-list hoverable>
            <n-list-item v-for="(chain, index) in jiraResult.code_context.call_chains" :key="index">
              <template #header>
                <n-text strong>{{ chain.api_path }}</n-text>
              </template>
              <tree-view :data="chain.call_chain.call_chain" />
            </n-list-item>
          </n-list>
        </n-card>

        <!-- Trace Data Section -->
        <n-card
          v-if="jiraResult.code_context?.trace_data"
          title="链路追踪数据"
          embedded
          class="section-card"
        >
          <n-descriptions label-placement="top" :column="2">
            <n-descriptions-item label="Trace ID">
              <n-space>
                <n-text>{{ jiraResult.code_context.trace_data.trace_id }}</n-text>
                <n-button
                  size="tiny"
                  tag="a"
                  :href="'https://devops.souche-inc.com/#/optimus/log'"
                  target="_blank"
                  type="primary"
                >
                  日志平台
                </n-button>
              </n-space>
            </n-descriptions-item>
            <n-descriptions-item label="Span 数量">
              {{ jiraResult.code_context.trace_data.span_count }}
            </n-descriptions-item>
            <n-descriptions-item label="包含 SQL">
              {{ jiraResult.code_context.trace_data.has_sql ? '是' : '否' }}
            </n-descriptions-item>
          </n-descriptions>
        </n-card>
      </template>

      <n-empty v-else description="暂无分析结果" />
    </n-spin>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useAnalyzerStore } from '../stores/analyzer'
import TreeView from './TreeView.vue'
import GraphView from './GraphView.vue'

const store = useAnalyzerStore()

const loading = computed(() => store.loading)
const jiraResult = computed(() => store.jiraResult)

function getStatusType(status) {
  const statusMap = {
    'Open': 'warning',
    'In Progress': 'info',
    'Resolved': 'success',
    'Closed': 'default'
  }
  return statusMap[status] || 'default'
}

function formatDate(dateStr) {
  if (!dateStr) return ''
  return new Date(dateStr).toLocaleString()
}

function getFileName(filePath) {
  if (!filePath) return ''
  return filePath.split('/').pop()
}

function formatFileSize(bytes) {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  while (bytes >= 1024 && i < units.length - 1) {
    bytes /= 1024
    i++
  }
  return `${bytes.toFixed(1)} ${units[i]}`
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

.summary-text {
  font-size: 14px;
  line-height: 1.6;
}

.cause-suggestion {
  margin-top: 8px;
  color: var(--n-text-color-2);
}

.cause-analysis {
  margin-top: 8px;
  color: var(--n-text-color-1);
  white-space: pre-wrap;
}

.evidence-label {
  font-size: 12px;
  color: var(--n-text-color-3);
  margin-top: 8px;
}

.ascii-view {
  background: #f5f5f5;
  padding: 16px;
  border-radius: 4px;
  overflow-x: auto;
  font-family: monospace;
  font-size: 12px;
  line-height: 1.4;
}
</style>