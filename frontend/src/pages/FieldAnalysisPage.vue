<template>
  <div class="page-container">
    <h1 class="page-title">字段溯源分析</h1>

    <FieldAnalysisForm @result="handleResult" />
    <FieldTraceView v-if="result" :result="result" class="result-container" />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import FieldAnalysisForm from '../components/FieldAnalysisForm.vue'
import FieldTraceView from '../components/FieldTraceView.vue'

const result = ref(null)

function handleResult(data) {
  result.value = data
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

.result-container {
  margin-top: 24px;
}
</style>
