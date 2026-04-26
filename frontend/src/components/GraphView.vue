<template>
  <div class="graph-view">
    <n-empty v-if="!callChain || callChain.length === 0" description="暂无分析结果" />
    <div v-else class="graph-container">
      <VueFlow
        v-model:nodes="nodes"
        v-model:edges="edges"
        :nodes-draggable="false"
        :nodes-connectable="false"
        :elements-selectable="true"
        fit-view-on-init
        class="vue-flow"
        @node-click="handleNodeClick"
      >
        <template #node-layer="{ data }">
          <div class="flow-node" :style="{ backgroundColor: data.color }">
            <div class="node-layer">{{ data.layer }}</div>
            <div class="node-class">{{ data.class_name }}</div>
            <div class="node-method">{{ data.method_name }}()</div>
          </div>
        </template>

        <Background pattern-color="#aaa" :gap="16" />
        <MiniMap />
      </VueFlow>

      <n-popover
        v-if="tooltipVisible"
        v-model:show="tooltipVisible"
        trigger="manual"
        placement="right"
        :x="tooltipX"
        :y="tooltipY"
      >
        <template #trigger>
          <span />
        </template>
        <div class="tooltip-content">
          <div><strong>Class:</strong> {{ tooltipData.class_name }}</div>
          <div><strong>Method:</strong> {{ tooltipData.method_name }}()</div>
          <div><strong>File:</strong> {{ tooltipData.file_path }}</div>
          <div><strong>Line:</strong> {{ tooltipData.line_number }}</div>
        </div>
      </n-popover>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { VueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { MiniMap } from '@vue-flow/minimap'
import '@vue-flow/core/dist/style.css'

const props = defineProps({
  callChain: {
    type: Array,
    default: () => []
  }
})

const tooltipVisible = ref(false)
const tooltipX = ref(0)
const tooltipY = ref(0)
const tooltipData = ref({})

const layerColors = {
  Controller: '#3b82f6',
  Service: '#22c55e',
  Internal: '#9ca3af',
  DAO: '#f97316',
  SQL: '#ef4444'
}

function buildGraphData(callChain) {
  if (!callChain || callChain.length === 0) return { nodes: [], edges: [] }

  const nodes = []
  const edges = []
  const nodeMap = new Map()

  let xOffset = 0
  const xStep = 250
  const yStep = 80

  callChain.forEach((node, idx) => {
    const key = `${node.layer}-${node.class_name}-${node.method_name}-${node.line_number}-${idx}`
    nodeMap.set(key, node)
  })

  const levelMap = new Map()
  const visited = new Set()

  function assignLevels(node, level) {
    const key = `${node.layer}-${node.class_name}-${node.method_name}-${node.line_number}-${callChain.indexOf(node)}`
    if (visited.has(key)) return
    visited.add(key)

    const existing = levelMap.get(key)
    if (existing !== undefined && existing >= level) return

    levelMap.set(key, level)
    if (node.children) {
      node.children.forEach(child => assignLevels(child, level + 1))
    }
  }

  const entryNode = callChain.find(n => n.is_entry) || callChain[0]
  assignLevels(entryNode, 0)
  callChain.forEach(node => {
    const key = `${node.layer}-${node.class_name}-${node.method_name}-${node.line_number}-${callChain.indexOf(node)}`
    if (!levelMap.has(key)) levelMap.set(key, 0)
  })

  const nodesByLevel = new Map()
  levelMap.forEach((level, key) => {
    if (!nodesByLevel.has(level)) nodesByLevel.set(level, [])
    nodesByLevel.set(level, [...nodesByLevel.get(level), key])
  })

  nodesByLevel.forEach((keys, level) => {
    keys.forEach((key, idx) => {
      const node = nodeMap.get(key)
      if (!node) return

      const x = level * xStep
      const y = idx * yStep

      nodes.push({
        id: key,
        type: 'layer',
        position: { x, y },
        data: {
          ...node,
          color: layerColors[node.layer] || '#9ca3af'
        }
      })
    })
  })

  const childMap = new Map()
  callChain.forEach((node, idx) => {
    const parentKey = `${node.layer}-${node.class_name}-${node.method_name}-${node.line_number}-${idx}`
    if (node.children) {
      node.children.forEach(child => {
        const childKey = `${child.layer}-${child.class_name}-${child.method_name}-${child.line_number}-${callChain.indexOf(child)}`
        if (!childMap.has(parentKey)) childMap.set(parentKey, [])
        childMap.set(parentKey, [...childMap.get(parentKey), childKey])
      })
    }
  })

  childMap.forEach((childKeys, parentKey) => {
    if (nodes.find(n => n.id === parentKey)) {
      childKeys.forEach(childKey => {
        if (nodes.find(n => n.id === childKey)) {
          edges.push({
            id: `${parentKey}-${childKey}`,
            source: parentKey,
            target: childKey,
            type: 'smoothstep',
            style: { stroke: '#999', strokeWidth: 2 }
          })
        }
      })
    }
  })

  return { nodes, edges }
}

const graphData = computed(() => buildGraphData(props.callChain))
const nodes = computed(() => graphData.value.nodes)
const edges = computed(() => graphData.value.edges)

function handleNodeClick(event) {
  const nodeData = event.node.data
  tooltipData.value = {
    class_name: nodeData.class_name,
    method_name: nodeData.method_name,
    file_path: nodeData.file_path,
    line_number: nodeData.line_number
  }
  tooltipX.value = event.event.clientX + 10
  tooltipY.value = event.event.clientY + 10
  tooltipVisible.value = true
}
</script>

<style scoped>
.graph-view {
  padding: 16px 0;
}

.graph-container {
  height: 500px;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  overflow: hidden;
}

.vue-flow {
  width: 100%;
  height: 100%;
}

.flow-node {
  padding: 10px 14px;
  border-radius: 8px;
  color: white;
  min-width: 140px;
  text-align: center;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

.node-layer {
  font-size: 10px;
  opacity: 0.85;
  margin-bottom: 4px;
}

.node-class {
  font-size: 13px;
  font-weight: 600;
}

.node-method {
  font-size: 12px;
  opacity: 0.9;
}

.tooltip-content {
  font-size: 12px;
  line-height: 1.6;
  max-width: 400px;
}

.tooltip-content strong {
  color: #666;
}
</style>