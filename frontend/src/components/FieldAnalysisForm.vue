<template>
  <n-card title="字段溯源分析" embedded>
    <n-form ref="formRef" :model="formValue" :rules="rules" label-placement="top">
      <n-grid :cols="3" :x-gap="16" responsive="screen" item-responsive>
        <n-gi span="1">
          <n-form-item label="项目名" path="projectName">
            <n-input
              v-model:value="formValue.projectName"
              placeholder="如 super-mario"
              @keydown.enter="handleAnalyze"
            />
          </n-form-item>
        </n-gi>
        <n-gi span="1">
          <n-form-item label="接口路径" path="apiPath">
            <n-input
              v-model:value="formValue.apiPath"
              placeholder="如 /v1/customer/getById"
              @keydown.enter="handleAnalyze"
            />
          </n-form-item>
        </n-gi>
        <n-gi span="1">
          <n-form-item label="Java 方法名" path="methodName">
            <n-input
              v-model:value="formValue.methodName"
              placeholder="如 getCustomerById"
              @keydown.enter="handleAnalyze"
            />
          </n-form-item>
        </n-gi>
      </n-grid>

      <n-grid :cols="3" :x-gap="16" responsive="screen" item-responsive>
        <n-gi span="1">
          <n-form-item label="响应字段路径" path="fieldPath">
            <n-input
              v-model:value="formValue.fieldPath"
              placeholder="如 data.userId 或 data.list[0].name"
              @keydown.enter="handleAnalyze"
            />
          </n-form-item>
        </n-gi>
      </n-grid>

      <n-space justify="end">
        <n-button type="primary" :loading="loading" @click="handleAnalyze">
          开始分析
        </n-button>
      </n-space>
    </n-form>

    <n-alert v-if="error" type="error" title="分析失败" style="margin-top: 16px">
      {{ error }}
    </n-alert>
  </n-card>
</template>

<script setup>
import { ref } from 'vue'
import { analyzeField } from '../api'

const emit = defineEmits(['result'])

const formRef = ref(null)
const loading = ref(false)
const error = ref(null)

const formValue = ref({
  projectName: '',
  apiPath: '',
  methodName: '',
  fieldPath: ''
})

function validateApiOrMethod(rule, value) {
  if (!formValue.value.apiPath && !formValue.value.methodName) {
    return new Error('接口路径或 Java 方法名至少填写一个')
  }
  return true
}

const rules = {
  projectName: [
    { required: true, message: '请输入项目名', trigger: 'blur' }
  ],
  apiPath: [
    { validator: validateApiOrMethod, trigger: 'blur' }
  ],
  methodName: [
    { validator: validateApiOrMethod, trigger: 'blur' }
  ],
  fieldPath: [
    { required: true, message: '请输入响应字段路径', trigger: 'blur' }
  ]
}

async function handleAnalyze() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }

  loading.value = true
  error.value = null

  try {
    const res = await analyzeField({
      project_name: formValue.value.projectName,
      api_path: formValue.value.apiPath || null,
      method_name: formValue.value.methodName || null,
      field_path: formValue.value.fieldPath
    })
    emit('result', res.data)
  } catch (e) {
    error.value = e.response?.data?.detail || e.message || '分析失败'
  } finally {
    loading.value = false
  }
}
</script>