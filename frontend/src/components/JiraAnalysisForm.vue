<template>
  <n-card title="JIRA 问题分析" embedded>
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

      <n-grid :cols="2" :x-gap="16" responsive="screen" item-responsive>
        <n-gi span="1">
          <n-form-item label="Git 地址" path="repoUrl">
            <n-input
              v-model:value="formValue.repoUrl"
              placeholder="如: https://github.com/user/repo.git"
              clearable
            />
          </n-form-item>
        </n-gi>
        <n-gi span="1">
          <n-form-item label="分支 (可选，默认 main)" path="ref">
            <n-input
              v-model:value="formValue.ref"
              placeholder="main"
              clearable
            />
          </n-form-item>
        </n-gi>
      </n-grid>

      <n-grid :cols="3" :x-gap="16" responsive="screen" item-responsive>
        <n-gi span="1">
          <n-form-item label="Trace ID (可选)" path="traceId">
            <n-space align="end">
              <n-input v-model:value="formValue.traceId" placeholder="Trace ID" style="flex: 1" />
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
          <n-form-item label="日期 (可选)" path="traceDate">
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
          分析
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
  repoUrl: '',
  ref: 'master',
  traceId: '',
  traceDate: null,
  cookies: ''
})

const rules = {
  jiraUrl: { required: true, message: '请输入 JIRA 地址', trigger: 'input' }
}

const loading = computed(() => store.loading)
const error = computed(() => store.error)

function handleAnalyze() {
  formRef.value?.validate((errors) => {
    if (errors) return

    const params = {
      jira_url: formValue.value.jiraUrl.trim()
    }

    if (formValue.value.repoUrl) params.repo_url = formValue.value.repoUrl.trim()
    if (formValue.value.ref) params.ref = formValue.value.ref
    if (formValue.value.traceId) params.trace_id = formValue.value.traceId
    if (formValue.value.traceDate) {
      const d = new Date(formValue.value.traceDate)
      params.trace_date = d.toISOString().split('T')[0]
    }
    if (formValue.value.cookies) params.cookies = formValue.value.cookies

    store.analyzeJiraIssue(params)
  })
}
</script>