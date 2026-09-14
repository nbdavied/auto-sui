<template>
  <!--
    账本里命中流水的小卡片。鼠标悬停触发,展示分类、对方账户、时间等,
    比对账时比一行"支出 14.9"信息量更大。
  -->
  <div class="matched">
    <div class="header">
      <el-tag :type="headerTag" size="small">{{ typeName(matched.tranType) }}</el-tag>
      <span class="amount">{{ matched.itemAmount }}</span>
    </div>

    <dl class="rows">
      <div v-if="matched.detailRemark" class="row">
        <dt>备注</dt>
        <dd>{{ matched.detailRemark }}</dd>
      </div>
      <div v-if="timeText" class="row">
        <dt>时间</dt>
        <dd>{{ timeText }}</dd>
      </div>
      <div v-if="matched.detailAccountName" class="row">
        <dt>本账户</dt>
        <dd>{{ matched.detailAccountName }}</dd>
      </div>
      <!--
        支出/收入时,商户就是"对方"概念。商户为空就退化到备注里的"主体"。
        转账时单独列转出/转入,语义更准。
      -->
      <div v-if="matched.tranType === 2" class="row">
        <dt>转出</dt>
        <dd>{{ matched.detailFromAccountName || matched.detailAccountName || '-' }}</dd>
      </div>
      <div v-if="matched.tranType === 2" class="row">
        <dt>转入</dt>
        <dd>{{ matched.detailToAccountName || '-' }}</dd>
      </div>
      <div v-else-if="matched.detailMerchant" class="row">
        <dt>对方</dt>
        <dd>{{ matched.detailMerchant }}</dd>
      </div>
      <div v-if="matched.detailCategoryName" class="row">
        <dt>分类</dt>
        <dd>{{ matched.detailCategoryName }}</dd>
      </div>
      <div v-if="matched.detailMemberName" class="row">
        <dt>成员</dt>
        <dd>{{ matched.detailMemberName }}</dd>
      </div>
      <div v-if="matched.tranId" class="row">
        <dt>流水 id</dt>
        <dd class="mono">{{ matched.tranId }}</dd>
      </div>
    </dl>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  matched: { type: Object, required: true }
})

function typeName(t) {
  return { 1: '支出', 2: '转账', 5: '收入' }[t] || '-'
}

// 标签配色区分支出/收入/转账,信息密度高一点
const headerTag = computed(() => {
  return { 1: 'danger', 5: 'success', 2: 'warning' }[props.matched.tranType] || 'info'
})

// 后端 detailTransactionTime 是毫秒或秒的数字字符串;空值兜底
const timeText = computed(() => {
  const t = props.matched.detailTransactionTime
  if (!t) return ''
  let d
  try {
    const n = Number(t)
    if (!isFinite(n) || n <= 0) return ''
    d = new Date(n > 1e12 ? n : n * 1000)
  } catch (e) {
    return ''
  }
  if (isNaN(d.getTime())) return ''
  const pad = x => String(x).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
         `${pad(d.getHours())}:${pad(d.getMinutes())}`
})
</script>

<style scoped>
.matched {
  font-size: 13px;
  line-height: 1.5;
}
.header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  padding-bottom: 8px;
  border-bottom: 1px dashed #ebeef5;
}
.amount {
  font-weight: 600;
  font-size: 15px;
  color: #303133;
}
.rows {
  margin: 0;
}
.row {
  display: flex;
  gap: 12px;
  padding: 3px 0;
}
.row dt {
  flex: 0 0 56px;
  color: #909399;
  font-size: 12px;
}
.row dd {
  flex: 1;
  margin: 0;
  color: #303133;
  word-break: break-all;
}
.mono {
  font-family: ui-monospace, Menlo, Consolas, monospace;
  font-size: 12px;
  color: #606266;
}
</style>
