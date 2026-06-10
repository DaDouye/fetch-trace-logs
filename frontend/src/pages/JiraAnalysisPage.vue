<template>
  <div class="page-container">
    <h1 class="page-title">JIRA 问题分析工具</h1>

    <JiraAnalysisForm />
    <JiraAnalysisView />
  </div>
</template>

<script setup>
import JiraAnalysisForm from '../components/JiraAnalysisForm.vue'
import JiraAnalysisView from '../components/JiraAnalysisView.vue'
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
