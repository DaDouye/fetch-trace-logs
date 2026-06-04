<template>
  <n-card title="生成故障初筛卡片" embedded>
    <n-form ref="formRef" :model="formValue" :rules="rules" label-placement="top">
      <n-grid :cols="5" :x-gap="16" responsive="screen" item-responsive>
        <n-gi span="3">
          <n-form-item label="JIRA 地址" path="jiraUrl">
            <n-input
              v-model:value="formValue.jiraUrl"
              placeholder="如: https://jira.souche-inc.com/browse/PROJ-123"
              @keydown.enter="handleAnalyze"
            />
          </n-form-item>
        </n-gi>
      </n-grid>

      <n-grid :cols="3" :x-gap="16" responsive="screen" item-responsive>
        <n-gi span="1">
          <n-form-item label="环境" path="environment">
            <n-select
              v-model:value="formValue.environment"
              :options="environmentOptions"
              placeholder="选择环境"
            />
          </n-form-item>
        </n-gi>
        <n-gi span="1">
          <n-form-item label="开始时间" path="startTime">
            <n-date-picker
              v-model:value="formValue.startTime"
              type="datetime"
              placeholder="选择开始时间"
              style="width: 100%"
              clearable
            />
          </n-form-item>
        </n-gi>
        <n-gi span="1">
          <n-form-item label="结束时间" path="endTime">
            <n-date-picker
              v-model:value="formValue.endTime"
              type="datetime"
              placeholder="选择结束时间"
              style="width: 100%"
              clearable
            />
          </n-form-item>
        </n-gi>
      </n-grid>

      <n-grid :cols="5" responsive="screen" item-responsive>
        <n-gi span="3">
          <n-form-item label="服务范围（可选）" path="services">
            <n-dynamic-input
              v-model:value="formValue.services"
              :min="1"
              placeholder="服务名，例如 super-mario"
            />
          </n-form-item>
        </n-gi>
      </n-grid>

      <n-grid :cols="5" responsive="screen" item-responsive>
        <n-gi span="3">
          <n-form-item label="接口" path="interfaces">
            <n-dynamic-input
              v-model:value="formValue.interfaces"
              :min="1"
              placeholder="接口路径，例如 /v1/crm/customerViewAction/queryCustomer.json"
            />
          </n-form-item>
        </n-gi>
      </n-grid>

      <n-grid :cols="3" :x-gap="16" responsive="screen" item-responsive>
        <n-gi span="2">
          <n-form-item label="关联仓库（可选，用于补充排查证据）" path="repoUrls">
            <n-dynamic-input
              class="repo-input-list"
              v-model:value="formValue.repoUrls"
              :min="1"
              preset="pair"
              :on-create="createRepoInput"
              key-placeholder="仓库URL"
              value-placeholder="分支，默认master"
            />
          </n-form-item>
        </n-gi>
      </n-grid>

      <n-grid :cols="5" :x-gap="4" responsive="screen" item-responsive>
        <n-gi span="2">
          <n-form-item label="Trace ID (可选)" path="traceId">
            <n-space align="end">
              <n-input v-model:value="formValue.traceId" placeholder="可留空，系统会尝试从 Jira 识别" style="flex: 1" />
              <n-button
                size="small"
                tag="a"
                href="https://devops.souche-inc.com/#/optimus/log"
                target="_blank"
                type="primary"
              >
                日志平台
              </n-button>
            </n-space>
          </n-form-item>
        </n-gi>
        <n-gi span="3">
          <n-form-item label="Cookies (可选)" path="cookies">
            <n-input
              v-model:value="formValue.cookies"
              placeholder="认证 Cookies"
            />
          </n-form-item>
        </n-gi>
      </n-grid>

      <n-space justify="end">
        <n-button type="primary" :loading="loading" @click="handleAnalyze">
          生成初筛卡片
        </n-button>
      </n-space>
    </n-form>

    <n-alert v-if="error" type="error" title="分析失败" style="margin-top: 16px">
      {{ error }}
    </n-alert>
  </n-card>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useAnalyzerStore } from '../stores/analyzer'

const store = useAnalyzerStore()

const formRef = ref(null)
const defaultCookies = '_user_iid=31893307; security-ref=cybertron-cooperate; isDingDing=true; tracknick=13655815401; _security_token_inc=91780541123170922;'
const formValue = ref({
  jiraUrl: '',
  environment: null,
  startTime: null,
  endTime: null,
  services: [''],
  interfaces: [''],
  repoUrls: [{ key: '', value: 'master' }],
  traceId: '',
  cookies: defaultCookies
})

const rules = {
  jiraUrl: { required: true, message: '请输入 JIRA 地址', trigger: 'input' },
  environment: { required: true, message: '请选择环境', trigger: 'change' },
  startTime: { required: true, type: 'number', message: '请选择开始时间', trigger: 'change' },
  endTime: { required: true, type: 'number', message: '请选择结束时间', trigger: 'change' }
}

const loading = computed(() => store.loading)
const error = computed(() => store.error)

const environmentOptions = [
  { label: '生产环境', value: '生产环境' },
  { label: '预发环境', value: '预发环境' },
  { label: '测试环境', value: '测试环境' }
]

function formatDateTime(value) {
  if (!value) return ''
  return new Date(value).toLocaleString()
}

function formatLocalDate(value) {
  if (!value) return ''
  const date = new Date(value)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function inferTraceDateFromTraceId(traceId) {
  const match = String(traceId || '').trim().match(/^(\d{13})_/)
  if (!match) return ''
  const timestamp = Number(match[1])
  if (!Number.isFinite(timestamp)) return ''
  return formatLocalDate(timestamp)
}

function parseServices(items) {
  return (items || [])
    .flatMap(item => String(item || '').split(/[\n,，]/))
    .map(item => item.trim())
    .filter(Boolean)
}

function parseInterfaces(items) {
  return (items || [])
    .flatMap(item => String(item || '').split(/[\n,，]/))
    .map(item => item.trim())
    .filter(Boolean)
}

function createRepoInput() {
  return { key: '', value: 'master' }
}

function handleAnalyze() {
  formRef.value?.validate((errors) => {
    if (errors) return

    const services = parseServices(formValue.value.services)
    const interfaces = parseInterfaces(formValue.value.interfaces)
    const params = {
      jira_url: formValue.value.jiraUrl.trim(),
      environment: formValue.value.environment,
      time_window: {
        start: formatDateTime(formValue.value.startTime),
        end: formatDateTime(formValue.value.endTime)
      },
      services,
      extra_clues: interfaces.join('\n'),
      use_ai: true
    }

    // 处理多仓库
    const validRepos = formValue.value.repoUrls.filter(r => isRepoUrl(r.key))
    if (validRepos.length > 0) {
      params.repo_urls = validRepos.map(r => ({
        repo_url: r.key.trim(),
        ref: r.value?.trim() || 'master'
      }))
    }

    if (formValue.value.traceId) {
      params.trace_id = formValue.value.traceId.trim()
      const inferredTraceDate = inferTraceDateFromTraceId(params.trace_id)
      if (inferredTraceDate) params.trace_date = inferredTraceDate
    }
    if (formValue.value.cookies) params.cookies = formValue.value.cookies

    store.analyzeJiraIssue(params)
  })
}

function isRepoUrl(value) {
  if (!value) return false
  const text = value.trim()
  return (
    text.startsWith('http://') ||
    text.startsWith('https://') ||
    text.startsWith('git@') ||
    text.startsWith('ssh://')
  )
}
</script>

<style scoped>
.repo-input-list :deep(.n-dynamic-input-pair-input:first-child) {
  flex: 2 1 0;
}

.repo-input-list :deep(.n-dynamic-input-pair-input:nth-child(2)) {
  flex: 1 1 0;
}
</style>
