<template>
  <n-card title="溯源结果" embedded>
    <!-- 错误/部分结果提示 -->
    <n-alert v-if="result.error" type="warning" title="提示" style="margin-bottom: 16px">
      {{ result.error }}
    </n-alert>

    <!-- 概览信息 -->
    <div class="overview">
      <n-descriptions bordered :column="2" size="small">
        <n-descriptions-item label="字段路径">{{ result.field_path }}</n-descriptions-item>
        <n-descriptions-item label="目标字段">{{ result.target_field }} ({{ result.target_field_type }})</n-descriptions-item>
        <n-descriptions-item label="DTO 类">{{ result.dto_class }}</n-descriptions-item>
        <n-descriptions-item label="DTO 文件">{{ result.dto_file || '未找到' }}</n-descriptions-item>
        <n-descriptions-item v-if="result.wrapper_class" label="包装类">{{ result.wrapper_class }}</n-descriptions-item>
        <n-descriptions-item label="Controller">
          {{ result.controller?.class_name }}.{{ result.controller?.method_name }}()
        </n-descriptions-item>
      </n-descriptions>
    </div>

    <!-- 路径解析 -->
    <div v-if="result.path_segments?.length" class="section">
      <h3 class="section-title">JSON 路径解析</h3>
      <n-timeline>
        <n-timeline-item
          v-for="(seg, idx) in result.path_segments"
          :key="idx"
          :type="seg.error ? 'error' : seg.role === 'wrapper' ? 'info' : 'success'"
          :title="seg.segment"
        >
          <template v-if="seg.error">
            <n-text type="error">{{ seg.error }}</n-text>
          </template>
          <template v-else-if="seg.role === 'wrapper'">
            <n-text depth="3">{{ seg.note }}</n-text>
          </template>
          <template v-else>
            <div>类: {{ seg.class }}</div>
            <div>字段: {{ seg.field }} ({{ seg.field_type }})</div>
            <div v-if="seg.json_name && seg.json_name !== seg.field">
              JSON 映射: {{ seg.json_name }} → {{ seg.field }}
              <n-tag v-if="seg.match_type === 'snake_case'" size="tiny" type="info">驼峰转换</n-tag>
            </div>
            <div v-if="seg.array_index !== undefined">数组下标: [{{ seg.array_index }}]</div>
            <div v-if="seg.annotations" class="annotations">注解: {{ seg.annotations }}</div>
          </template>
        </n-timeline-item>
      </n-timeline>
    </div>

    <!-- 赋值追踪 -->
    <div v-if="result.assignments?.length" class="section">
      <h3 class="section-title">赋值点分析</h3>
      <div v-for="(assign, idx) in result.assignments" :key="idx" class="assignment-card">
        <n-card size="small" :bordered="true" embedded>
          <template #header>
            <n-space align="center">
              <n-tag :type="assign.speculative ? 'warning' : 'success'" size="small">
                {{ assign.pattern }}
              </n-tag>
              <span>{{ assign.class_name }}.{{ assign.method_name }}()</span>
              <n-tag v-if="assign.speculative" type="warning" size="small" :bordered="true">
                推测
              </n-tag>
            </n-space>
          </template>

          <div class="code-snippet">{{ assign.code }}</div>

          <div v-if="assign.file_path" class="file-location">
            文件: {{ assign.file_path }}
          </div>

          <div v-if="assign.param_source?.source_class" class="source-info">
            <n-text depth="2">数据来源: </n-text>
            <n-text>{{ assign.param_source.source_class }}.{{ assign.param_source.source_field }}</n-text>
            <span v-if="assign.param_source.expression">
              ({{ assign.param_source.expression }})
            </span>
          </div>

          <div v-if="assign.note" class="note">
            <n-text depth="3" italic>{{ assign.note }}</n-text>
          </div>

          <!-- 推测匹配详情 -->
          <div v-if="assign.speculative_match" class="speculative-detail">
            <n-divider />
            <n-text type="warning">推测依据：</n-text>
            <div>源类型: {{ assign.speculative_match.source_type }}</div>
            <div v-if="assign.speculative_match.source_file">
              文件: {{ assign.speculative_match.source_file }}
            </div>
            <div v-if="assign.speculative_match.matched_fields?.length">
              <div v-for="(mf, mi) in assign.speculative_match.matched_fields" :key="mi" class="matched-field">
                → {{ mf.source_field }} ({{ mf.source_type }})
                <div v-if="mf.sql_info?.related_sqls" class="sql-block">
                  <div v-for="(sql, method) in mf.sql_info.related_sqls" :key="method">
                    <n-text code>{{ method }}: {{ sql }}</n-text>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </n-card>
      </div>
    </div>

    <!-- 未找到赋值 -->
    <n-alert v-if="!result.assignments?.length && !result.error" type="info" title="未找到赋值点" style="margin-top: 16px">
      在当前 Service 方法中未找到对 {{ result.target_field }} 字段的直接赋值。
    </n-alert>

    <!-- 搜索诊断 -->
    <n-collapse v-if="result.search_debug" class="section">
      <n-collapse-item title="搜索诊断信息" name="debug">
        <n-descriptions bordered :column="1" size="small">
          <n-descriptions-item label="Controller 文件">{{ result.search_debug.controller_file || '未找到' }}</n-descriptions-item>
          <n-descriptions-item label="方法体提取">
            <n-tag :type="result.search_debug.method_body_extracted ? 'success' : 'error'" size="small">
              {{ result.search_debug.method_body_extracted ? '成功' : '失败（使用整个文件）' }}
            </n-tag>
          </n-descriptions-item>
          <n-descriptions-item v-if="result.search_debug.query_params_applied" label="查询参数裁剪">
            <n-tag type="info" size="small">已应用</n-tag>
            {{ JSON.stringify(result.search_debug.query_params) }}
          </n-descriptions-item>
          <n-descriptions-item label="发现的 Service 调用">
            <template v-if="result.search_debug.service_calls_found?.length">
              <n-tag v-for="call in result.search_debug.service_calls_found" :key="call" size="small" style="margin: 2px">
                {{ call }}
              </n-tag>
            </template>
            <n-text v-else depth="3">无</n-text>
          </n-descriptions-item>
          <n-descriptions-item label="搜索的文件">
            <div v-for="sf in result.search_debug.searched_files" :key="sf.call" style="margin-bottom: 4px">
              <n-text>{{ sf.call }}</n-text>
              <n-text depth="3"> → {{ sf.impl_path || '未找到实现' }}</n-text>
            </div>
            <n-text v-if="!result.search_debug.searched_files?.length" depth="3">无</n-text>
          </n-descriptions-item>
          <n-descriptions-item label="回退全局搜索">
            <n-tag :type="result.search_debug.used_fallback ? 'warning' : 'success'" size="small">
              {{ result.search_debug.used_fallback ? '已触发' : '未触发' }}
            </n-tag>
          </n-descriptions-item>
        </n-descriptions>
      </n-collapse-item>
    </n-collapse>

    <!-- 追踪链 -->
    <div v-if="result.trace_chain?.length" class="section">
      <h3 class="section-title">数据源追踪</h3>
      <div v-for="(trace, idx) in result.trace_chain" :key="idx" class="trace-card">
        <n-card size="small" :bordered="true" embedded>
          <n-descriptions bordered :column="2" size="small">
            <n-descriptions-item label="来源类">{{ trace.source_class }}</n-descriptions-item>
            <n-descriptions-item label="来源字段">{{ trace.source_field }}</n-descriptions-item>
            <n-descriptions-item v-if="trace.source_file" label="文件">{{ trace.source_file }}</n-descriptions-item>
            <n-descriptions-item v-if="trace.db_mapping?.table" label="数据库表">
              {{ trace.db_mapping.table }}
            </n-descriptions-item>
            <n-descriptions-item v-if="trace.db_mapping" label="数据库字段">
              {{ trace.db_mapping.column }}
              <n-tag v-if="trace.db_mapping.is_primary_key" size="tiny" type="info">主键</n-tag>
            </n-descriptions-item>
          </n-descriptions>

          <!-- SQL 展示 -->
          <div v-if="trace.sql_info?.related_sqls && Object.keys(trace.sql_info.related_sqls).length" class="sql-section">
            <n-divider />
            <div class="sql-label">相关 SQL ({{ trace.sql_info.mapper }}):</div>
            <div v-for="(sql, method) in trace.sql_info.related_sqls" :key="method" class="sql-item">
              <n-text code>{{ method }}:</n-text>
              <n-code :code="sql" language="sql" />
            </div>
          </div>
        </n-card>
      </div>
    </div>
  </n-card>
</template>

<script setup>
defineProps({
  result: {
    type: Object,
    required: true
  }
})
</script>

<style scoped>
.overview {
  margin-bottom: 20px;
}

.section {
  margin-top: 24px;
}

.section-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 12px;
  color: #333;
}

.assignment-card {
  margin-bottom: 12px;
}

.code-snippet {
  font-family: monospace;
  background: #f5f5f5;
  padding: 8px 12px;
  border-radius: 4px;
  margin: 8px 0;
  font-size: 13px;
  color: #333;
  word-break: break-all;
}

.file-location {
  font-size: 12px;
  color: #999;
  margin-top: 4px;
}

.source-info {
  margin-top: 8px;
}

.note {
  margin-top: 4px;
}

.speculative-detail {
  margin-top: 8px;
  padding: 8px;
  background: #fffbe6;
  border-radius: 4px;
  font-size: 13px;
}

.matched-field {
  margin-top: 4px;
  padding-left: 8px;
}

.sql-block {
  margin-top: 4px;
  padding-left: 16px;
}

.trace-card {
  margin-bottom: 12px;
}

.sql-section {
  margin-top: 12px;
}

.sql-label {
  font-size: 13px;
  color: #666;
  margin-bottom: 8px;
}

.sql-item {
  margin-bottom: 8px;
}

.annotations {
  font-size: 12px;
  color: #999;
  font-family: monospace;
}
</style>