<template>
  <n-card title="调用链分析" embedded>
    <n-form ref="formRef" :model="formValue" :rules="rules" label-placement="top">
      <n-grid :cols="3" :x-gap="16" responsive="screen" item-responsive>
        <n-gi span="1">
          <n-form-item label="仓库" path="repoKey">
            <n-select
              v-model:value="formValue.repoKey"
              :options="repoOptions"
              placeholder="请选择仓库"
              filterable
            />
          </n-form-item>
        </n-gi>
        <n-gi span="2">
          <n-form-item label="API 路径" path="apiPath">
            <n-input
              v-model:value="formValue.apiPath"
              placeholder="如: /v1/customer/saveOrUpdate"
              @keydown.enter="handleAnalyze"
            />
          </n-form-item>
        </n-gi>
      </n-grid>

      <n-grid :cols="3" :x-gap="16" responsive="screen" item-responsive>
        <n-gi span="1">
          <n-form-item label="Trace ID (可选)" path="traceId">
            <n-input v-model:value="formValue.traceId" placeholder="Trace ID" />
          </n-form-item>
        </n-gi>
        <n-gi span="1">
          <n-form-item label="日期 (可选)" path="date">
            <n-date-picker
              v-model:value="formValue.date"
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
import { ref, computed, onMounted } from 'vue'
import { useAnalyzerStore } from '../stores/analyzer'

const store = useAnalyzerStore()

const formRef = ref(null)
const formValue = ref({
  repoKey: null,
  apiPath: '',
  traceId: '',
  date: null,
  cookies: ''
})

const rules = {
  repoKey: { required: true, message: '请选择仓库', trigger: 'change' },
  apiPath: { required: true, message: '请输入 API 路径', trigger: 'input' }
}

const repoOptions = computed(() =>
  store.repos.map(r => ({ label: r.name, value: r.key }))
)

const loading = computed(() => store.loading)
const error = computed(() => store.error)

onMounted(() => {
  store.loadRepos()
})

function handleAnalyze() {
  formRef.value?.validate((errors) => {
    if (errors) return

    const params = {
      api_path: formValue.value.apiPath.trim(),
      repo_key: formValue.value.repoKey
    }

    if (formValue.value.traceId) params.trace_id = formValue.value.traceId
    if (formValue.value.date) {
      const d = new Date(formValue.value.date)
      params.date = d.toISOString().split('T')[0]
    }
    if (formValue.value.cookies) params.cookies = formValue.value.cookies

    store.analyze(params)
  })
}
</script>