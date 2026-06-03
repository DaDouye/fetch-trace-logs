<template>
  <n-card title="生成故障初筛卡片" embedded>
    <n-form ref="formRef" :model="formValue" :rules="rules" label-placement="top">
      <n-grid :cols="3" :x-gap="16" responsive="screen" item-responsive>
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

      <n-grid :cols="4" :x-gap="16" responsive="screen" item-responsive>
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
        <n-gi span="1">
          <n-form-item label="问题类型" path="problemType">
            <n-select
              v-model:value="formValue.problemType"
              :options="problemTypeOptions"
              placeholder="选择类型"
            />
          </n-form-item>
        </n-gi>
      </n-grid>

      <n-grid :cols="2" :x-gap="16" responsive="screen" item-responsive>
        <n-gi span="1">
          <n-form-item label="服务范围" path="servicesText">
            <n-input
              v-model:value="formValue.servicesText"
              type="textarea"
              placeholder="填写需要排查的服务，多个服务用逗号或换行分隔"
              :autosize="{ minRows: 3, maxRows: 5 }"
            />
          </n-form-item>
        </n-gi>
        <n-gi span="1">
          <n-form-item label="补充线索（可选）" path="extraClues">
            <n-input
              v-model:value="formValue.extraClues"
              type="textarea"
              placeholder="例如接口名、错误关键词、用户反馈现象"
              :autosize="{ minRows: 3, maxRows: 5 }"
            />
          </n-form-item>
        </n-gi>
      </n-grid>

      <n-grid :cols="2" :x-gap="16" responsive="screen" item-responsive>
        <n-gi span="2">
          <n-form-item label="关联仓库（可选，用于补充排查证据）" path="repoUrls">
            <n-dynamic-input
              v-model:value="formValue.repoUrls"
              :min="0"
              preset="pair"
              key-placeholder="仓库URL"
              value-placeholder="commit SHA"
            />
          </n-form-item>
        </n-gi>
      </n-grid>

      <n-grid :cols="3" :x-gap="16" responsive="screen" item-responsive>
        <n-gi span="1">
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
        <n-gi span="1">
          <n-form-item label="Trace 日期（可选）" path="traceDate">
            <n-date-picker
              v-model:value="formValue.traceDate"
              type="date"
              placeholder="选择日期"
              style="width: 100%"
              clearable
            />
          </n-form-item>
        </n-gi>
        <n-gi span="1">
          <n-form-item label="Cookies (可选)" path="cookies">
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
const formValue = ref({
  jiraUrl: '',
  environment: null,
  startTime: null,
  endTime: null,
  problemType: null,
  servicesText: '',
  extraClues: '',
  repoUrls: [],
  traceId: '',
  traceDate: null,
  cookies: ''
})

const rules = {
  jiraUrl: { required: true, message: '请输入 JIRA 地址', trigger: 'input' },
  environment: { required: true, message: '请选择环境', trigger: 'change' },
  startTime: { required: true, type: 'number', message: '请选择开始时间', trigger: 'change' },
  endTime: { required: true, type: 'number', message: '请选择结束时间', trigger: 'change' },
  problemType: { required: true, message: '请选择问题类型', trigger: 'change' },
  servicesText: { required: true, message: '请输入服务范围', trigger: 'input' }
}

const loading = computed(() => store.loading)
const error = computed(() => store.error)

const environmentOptions = [
  { label: '生产环境', value: '生产环境' },
  { label: '预发环境', value: '预发环境' },
  { label: '测试环境', value: '测试环境' }
]

const problemTypeOptions = [
  { label: '接口异常', value: '接口异常' },
  { label: '页面异常', value: '页面异常' },
  { label: '性能变慢', value: '性能变慢' },
  { label: '数据异常', value: '数据异常' },
  { label: '任务异常', value: '任务异常' },
  { label: '其他', value: '其他' }
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

function parseServices(text) {
  return text
    .split(/[\n,，]/)
    .map(item => item.trim())
    .filter(Boolean)
}

function handleAnalyze() {
  formRef.value?.validate((errors) => {
    if (errors) return

    const services = parseServices(formValue.value.servicesText)
    const params = {
      jira_url: formValue.value.jiraUrl.trim(),
      environment: formValue.value.environment,
      time_window: {
        start: formatDateTime(formValue.value.startTime),
        end: formatDateTime(formValue.value.endTime)
      },
      problem_type: formValue.value.problemType,
      services,
      extra_clues: formValue.value.extraClues.trim(),
      use_ai: true
    }

    // 处理多仓库
    const validRepos = formValue.value.repoUrls.filter(r => isRepoUrl(r.key))
    if (validRepos.length > 0) {
      params.repo_urls = validRepos.map(r => ({
        repo_url: r.key.trim(),
        locked_ref: r.value?.trim()
      }))
    }

    if (formValue.value.traceId) params.trace_id = formValue.value.traceId
    if (formValue.value.traceDate) {
      params.trace_date = formatLocalDate(formValue.value.traceDate)
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
