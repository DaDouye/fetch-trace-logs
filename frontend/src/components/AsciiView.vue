<template>
  <div class="ascii-view">
    <n-empty v-if="!asciiGraph" description="暂无分析结果" />
    <pre v-else class="ascii-content">{{ asciiGraph }}</pre>
  </div>
</template>

<script setup>
defineProps({
  asciiGraph: {
    type: String,
    default: ''
  }
})
</script>

<style scoped>
.ascii-view {
  padding: 16px 0;
}

.ascii-content {
  background-color: #1e1e1e;
  color: #d4d4d4;
  padding: 16px;
  border-radius: 8px;
  font-family: 'Fira Code', 'Consolas', monospace;
  font-size: 13px;
  line-height: 1.5;
  overflow-x: auto;
  white-space: pre;
}
</style>