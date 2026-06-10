

<template>
  <div class="page-container">
    <h1 class="page-title">链路 SQL 分析工具</h1>

    <!-- 输入区 -->
    <n-card title="分析条件" embedded class="input-card">
      <n-form ref="formRef" :model="formValue" :rules="rules" label-placement="top">
        <n-grid :cols="2" :x-gap="16" responsive="screen" item-responsive>
          <n-gi span="1">
            <n-form-item label="Trace ID" path="traceId">
              <n-input
                v-model:value="formValue.traceId"
                placeholder="输入 Trace ID"
                @keydown.enter="handleAnalyze"
              />
            </n-form-item>
          </n-gi>
          <n-gi span="1">
            <n-form-item label="Cookies" path="cookies">
              <n-input
                v-model:value="formValue.cookies"
                type="password"
                placeholder="认证 Cookies"
                show-password-on="click"
              />
            </n-form-item>
          </n-gi>
        </n-grid>

        <n-space justify="end">
          <n-button type="primary" :loading="loading" @click="handleAnalyze">
            分析
          </n-button>
        </n-space>
      </n-form>

      <n-alert v-if="error" type="error" title="分析失败" style="margin-top: 16px">
        {{ error }}
      </n-alert>
    </n-card>

    <!-- 输出区 -->
    <div v-if="!loading && sqlList.length > 0" class="result-container">
      <div class="result-header">
        <h2>SQL 列表 ({{ sqlList.length }} 条)</h2>
        <n-space>
          <n-button size="small" @click="copyAllSql">复制全部</n-button>
        </n-space>
      </div>

      <div v-for="(item, index) in sqlList" :key="index" class="sql-card">
        <div class="sql-card-header">
          <div class="sql-info">
            <n-tag type="info" size="small">#{{ index + 1 }}</n-tag>
            <span class="db-name">{{ item.service_name || 'Unknown' }}</span>
            <span v-if="item.rid" class="db-port">{{ item.rid }}</span>
          </div>
          <div class="sql-meta">
            <n-tag v-if="item.is_batch" type="warning" size="small">批量</n-tag>
            <n-tag type="info" size="small">{{ item.duration_ms }}ms</n-tag>
            <n-button size="small" @click="copySql(item.sql)">复制</n-button>
          </div>
        </div>

        <n-divider />

        <div class="sql-section">
          <pre class="sql-content formatted">{{ item.sql }}</pre>
        </div>
      </div>
    </div>

    <!-- 空状态 -->
    <n-card v-else-if="!loading && analyzed && sqlList.length === 0" embedded class="empty-card">
      <n-empty description="未检测到 SQL 操作" />
    </n-card>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useTraceStore } from '../stores/traceStore'

const store = useTraceStore()

const formRef = ref(null)
const defaultCookies = '_user_iid=31893307; isDingDing=true; tracknick=13655815401; security-ref=trace; _security_token_inc=91780985077472176; acw_tc=781a97e317810713415557496ec8b1876b640d1676c0c3e30231e160596496;'
const formValue = ref({
  traceId: '',
  cookies: defaultCookies
})
const analyzed = ref(false)

const rules = {
  traceId: { required: true, message: '请输入 Trace ID', trigger: 'blur' },
  cookies: { required: true, message: '请输入 Cookies', trigger: 'blur' }
}

const loading = computed(() => store.loading)
const error = computed(() => store.error)
const sqlList = computed(() => store.sqlList)

function handleAnalyze() {
  formRef.value?.validate((errors) => {
    if (errors) return
    analyzed.value = true
    store.analyzeTrace(formValue.value.traceId, formValue.value.cookies)
  })
}

function copySql(sql) {
  navigator.clipboard.writeText(sql)
}

function copyAllSql() {
  const allSql = sqlList.value.map((item, i) => `-- SQL #${i + 1}\n${item.sql}`).join('\n\n')
  navigator.clipboard.writeText(allSql)
}
</script>

<style scoped>
.page-container {
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
}

.page-title {
  font-size: 24px;
  font-weight: 600;
  margin-bottom: 24px;
  color: #333;
}

.input-card {
  margin-bottom: 24px;
}

.result-container {
  margin-top: 16px;
}

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.result-header h2 {
  font-size: 18px;
  margin: 0;
}

.sql-card {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}

.sql-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.sql-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.db-name {
  font-weight: 500;
  color: #333;
}

.db-port {
  color: #666;
}

.sql-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.sql-section {
  margin-top: 12px;
}

.sql-label {
  font-size: 12px;
  color: #666;
  margin-bottom: 6px;
  font-weight: 500;
}

.sql-content {
  margin: 0;
  padding: 12px;
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.5;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

.sql-content.formatted {
  background: #1e1e1e;
  color: #d4d4d4;
}

.sql-content.original {
  background: #f6f8fa;
  color: #24292f;
}

.sql-content.params {
  background: #f6f8fa;
  color: #24292f;
  font-size: 12px;
}

.empty-card {
  margin-top: 16px;
}
</style>
