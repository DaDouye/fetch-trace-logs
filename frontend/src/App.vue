<template>
  <div class="page-container">
    <h1 class="page-title">调用链分析工具</h1>

    <AnalyzerForm />

    <div v-if="store.result" class="result-container">
      <n-tabs v-model:value="activeTab" type="line" animated>
        <n-tab-pane name="ascii" tab="ASCII 视图">
          <AsciiView :ascii-graph="store.result.ascii_graph" />
        </n-tab-pane>
        <n-tab-pane name="tree" tab="树状图">
          <TreeView :call-chain="store.result.call_chain" />
        </n-tab-pane>
        <n-tab-pane name="graph" tab="图形视图">
          <GraphView :call-chain="store.result.call_chain" />
        </n-tab-pane>
      </n-tabs>
    </div>

    <div v-if="store.result?.error" class="result-container">
      <n-alert type="warning" :title="store.result.error">
        {{ store.result.error }}
      </n-alert>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import AnalyzerForm from './components/AnalyzerForm.vue'
import AsciiView from './components/AsciiView.vue'
import TreeView from './components/TreeView.vue'
import GraphView from './components/GraphView.vue'
import { useAnalyzerStore } from './stores/analyzer'

const store = useAnalyzerStore()
const activeTab = ref('ascii')
</script>