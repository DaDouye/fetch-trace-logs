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

      <n-form-item label="补充线索（可选）" path="extraClues">
        <n-input
          v-model:value="formValue.extraClues"
          type="textarea"
          placeholder="例如接口名、错误关键词、用户反馈现象"
          :autosize="{ minRows: 3, maxRows: 5 }"
        />
      </n-form-item>

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
  extraClues: '',
  traceId: '',
  traceDate: null,
  cookies: ''
})

const rules = {
  jiraUrl: { required: true, message: '请输入 JIRA 地址', trigger: 'input' }
}

const loading = computed(() => store.loading)
const error = computed(() => store.error)

function formatLocalDate(value) {
  if (!value) return ''
  const date = new Date(value)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function handleAnalyze() {
  formRef.value?.validate((errors) => {
    if (errors) return

    const params = {
      jira_url: formValue.value.jiraUrl.trim(),
      extra_clues: formValue.value.extraClues.trim(),
      use_ai: true
    }

    if (formValue.value.traceId) params.trace_id = formValue.value.traceId
    if (formValue.value.traceDate) {
      params.trace_date = formatLocalDate(formValue.value.traceDate)
    }
    if (formValue.value.cookies) params.cookies = formValue.value.cookies

    store.analyzeJiraIssue(params)
  })
}
</script>
