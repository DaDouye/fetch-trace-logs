<template>
  <div class="tree-view">
    <n-empty v-if="!callChain || callChain.length === 0" description="暂无分析结果" />
    <div v-else class="tree-content">
      <TreeNode
        v-for="node in treeData"
        :key="node.key"
        :node="node"
        :default-expanded="true"
      />
    </div>

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
</template>

<script setup>
import { ref, computed, h, defineComponent } from 'vue'

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

let nodeKeyCounter = 0

function assignKeys(node) {
  if (!node) return
  node.key = `${node.layer}-${node.class_name}-${node.method_name}-${nodeKeyCounter++}`
  node.expanded = true
  if (node.children) {
    node.children.forEach(child => assignKeys(child))
  }
}

function buildTree(callChain) {
  if (!callChain || callChain.length === 0) return []

  // Serialized call_chain has nodes with nested `children` arrays.
  // Root is identified by is_entry: true.
  const root = callChain.find(n => n.is_entry) || callChain[0]
  if (!root) return []

  nodeKeyCounter = 0
  assignKeys(root)

  return [root]
}

const treeData = computed(() => buildTree(props.callChain))

function showTooltip(event, data) {
  tooltipData.value = data
  tooltipX.value = event.clientX + 10
  tooltipY.value = event.clientY + 10
  tooltipVisible.value = true
}

function hideTooltip() {
  tooltipVisible.value = false
}

const layerColors = {
  Controller: '#3b82f6',
  Service: '#22c55e',
  Internal: '#9ca3af',
  DAO: '#f97316',
  SQL: '#ef4444'
}

const TreeNode = defineComponent({
  name: 'TreeNode',
  props: {
    node: { type: Object, required: true },
    defaultExpanded: { type: Boolean, default: false },
    depth: { type: Number, default: 0 }
  },
  setup(props) {
    const expanded = ref(props.defaultExpanded)

    return () => {
      const node = props.node
      const hasChildren = node.children && node.children.length > 0
      const layerColor = layerColors[node.layer] || '#9ca3af'

      const children = []

      children.push(
        h('div', {
          class: 'tree-node',
          style: { paddingLeft: `${props.depth * 20}px` },
          onClick: (e) => {
            if (hasChildren) expanded.value = !expanded.value
            showTooltip(e, node)
          }
        }, [
          h('span', { class: 'expand-icon' }, hasChildren ? (expanded.value ? '▼' : '▶') : ' '),
          h('span', {
            class: 'layer-badge',
            style: { backgroundColor: layerColor }
          }, node.layer),
          h('span', { class: 'node-text' }, `${node.class_name}.${node.method_name}()`)
        ])
      )

      if (hasChildren && expanded.value) {
        node.children.forEach(child => {
          children.push(
            h(TreeNode, {
              node: child,
              depth: props.depth + 1,
              defaultExpanded: true,
              key: child.key
            })
          )
        })
      }

      if (node.sql) {
        children.push(
          h('div', {
            class: 'sql-node',
            style: { paddingLeft: `${(props.depth + 1) * 20 + 16}px` }
          }, [
            h('span', { class: 'layer-badge', style: { backgroundColor: '#ef4444' } }, 'SQL'),
            h('span', { class: 'sql-text' }, node.sql.length > 80 ? node.sql.substring(0, 80) + '...' : node.sql)
          ])
        )
      }

      return h('div', { class: 'tree-node-wrapper' }, children)
    }
  }
})
</script>

<style scoped>
.tree-view {
  padding: 16px 0;
}

.tree-content {
  font-family: 'Fira Code', 'Consolas', monospace;
  font-size: 13px;
}

.tree-node {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  cursor: pointer;
  border-radius: 4px;
}

.tree-node:hover {
  background-color: #f0f0f0;
}

.expand-icon {
  width: 16px;
  font-size: 10px;
  color: #666;
}

.layer-badge {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
  color: white;
  font-weight: 500;
}

.node-text {
  color: #333;
}

.sql-node {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}

.sql-text {
  color: #666;
  font-size: 12px;
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