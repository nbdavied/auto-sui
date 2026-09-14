<template>
  <el-dialog :model-value="modelValue" title="记账" width="640px"
             @update:model-value="v => emit('update:modelValue', v)">
    <el-form label-width="88px" v-if="detail">
      <el-form-item label="金额">
        <span class="amount">{{ detail.amount }}</span>
      </el-form-item>
      <el-form-item label="日期">
        <span>{{ formatDate(detail.date) }} {{ formatTime(detail.time) }}</span>
      </el-form-item>
      <el-form-item label="摘要">
        <span class="ellipsis">{{ detail.memo || detail.usage || detail.opAccName || '-' }}</span>
      </el-form-item>

      <el-form-item label="记账方式">
        <el-radio-group v-model="op">
          <el-radio-button value="payout">支出</el-radio-button>
          <el-radio-button value="income">收入</el-radio-button>
          <el-radio-button value="transfer">转账</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-form-item v-if="op === 'transfer'" label="对手账户">
        <el-select v-model="opSuiid" placeholder="选择对手账户" style="width:100%">
          <el-option v-for="a in accounts" :key="a.id" :label="a.name" :value="a.id" />
        </el-select>
      </el-form-item>
      <el-form-item v-else label="分类">
        <el-cascader v-model="catPath" :options="catOptions" style="width:100%"
                     :props="{ value: 'id', label: 'name', children: 'children', emitPath: true }"
                     placeholder="选择分类" />
      </el-form-item>

      <el-form-item label="备注">
        <el-input v-model="memo" />
      </el-form-item>

      <el-form-item label="存为规则">
        <el-checkbox v-model="saveRule">以后同类交易自动记账</el-checkbox>
      </el-form-item>

      <el-form-item v-if="saveRule" label="匹配条件">
        <!--
          结构化条件编辑器: 每行一个「字段 + 匹配方式 + 值」,多条之间是 AND。
          字段和匹配方式都用下拉框,避免用户手写任意代码 —— 后端也是白名单校验。
        -->
        <div class="conds">
          <div v-for="(c, i) in conditions" :key="i" class="cond-row">
            <el-select v-model="c.field" size="small" style="width:120px"
                       @change="onFieldChange(c)">
              <el-option v-for="f in api.ruleFields" :key="f.value"
                         :label="f.label" :value="f.value" />
            </el-select>
            <el-select v-model="c.match" size="small" style="width:110px">
              <el-option v-for="m in availableMatches(c)" :key="m.value"
                         :label="m.label" :value="m.value" />
            </el-select>
            <el-select v-if="c.field === 'transType' && c.match === 'eq'"
                       v-model="c.value" size="small" style="width:120px"
                       placeholder="收支">
              <el-option label="收入" value="income" />
              <el-option label="支出" value="payout" />
            </el-select>
            <el-input v-else v-model="c.value" size="small" style="width:160px"
                      placeholder="匹配值" />
            <el-button link type="danger"
                       :disabled="conditions.length === 1"
                       @click="removeCond(i)">删除</el-button>
          </div>
          <el-button link type="primary" @click="addCond">+ 添加条件</el-button>
          <div class="tip">
            多条件之间是「同时满足」关系；规则按优先级从高到低匹配。
          </div>
        </div>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="loading" @click="submit">确定记账</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api, formatDate, formatTime } from '../api.js'

const props = defineProps({
  modelValue: Boolean,
  detail: Object,
  accounts: Array,
  categories: Object,
  // 从外部预填的规则(命中规则时带入),用于一键按规则记账
  preselectRule: Object
})
const emit = defineEmits(['update:modelValue', 'submit'])

const op = ref('payout')
const catPath = ref([])
const opSuiid = ref('')
const memo = ref('')
const saveRule = ref(false)
const conditions = ref([defaultCond()])
const loading = ref(false)

function defaultCond() {
  return { field: 'opAccName', match: 'eq', value: '' }
}

// 在分类树里找 id === target 的路径(el-cascader 要的是从顶级到当前节点的 id 列表)
function findCatPath(node, target) {
  if (node.id === target) return [node.id]
  if (!node.children) return null
  for (const c of node.children) {
    const sub = findCatPath(c, target)
    if (sub) return [node.id, ...sub]
  }
  return null
}

// 数字字段(金额)能比大小;其他字段比大小没意义,前端收窄一下避免误导用户
const NUMERIC_FIELDS = new Set(['amount'])
function availableMatches(c) {
  if (NUMERIC_FIELDS.has(c.field)) {
    return [{ value: 'eq', label: '等于' }, { value: 'gt', label: '大于' },
            { value: 'lt', label: '小于' }]
  }
  return api.ruleMatches
}

// 切换字段时,如果旧的匹配方式不再适用,自动回落到「等于」
function onFieldChange(c) {
  const valid = availableMatches(c).some(m => m.value === c.match)
  if (!valid) c.match = NUMERIC_FIELDS.has(c.field) ? 'eq' : 'contains'
}

function addCond() {
  conditions.value.push(defaultCond())
}

function removeCond(i) {
  if (conditions.value.length === 1) return
  conditions.value.splice(i, 1)
}

// 根据当前交易自动生成一条「对手户名 + 收支方向」条件,改改就能存为规则
function presetConds(d) {
  const list = [{ field: 'transType', match: 'eq', value: d.transType || 'payout' }]
  if (d.opAccName) list.push({ field: 'opAccName', match: 'eq', value: d.opAccName })
  else if (d.opAccNo) list.push({ field: 'opAccNo', match: 'eq', value: d.opAccNo })
  else if (d.memo) list.push({ field: 'memo', match: 'contains', value: d.memo })
  return list
}

watch(() => props.modelValue, (v) => {
  if (!v || !props.detail) return
  const d = props.detail
  const rule = props.preselectRule
  op.value = (rule && rule.op) || (d.transType === 'income' ? 'income' : 'payout')
  catPath.value = []
  opSuiid.value = (rule && rule.op === 'transfer' && rule.opSuiid) || ''
  memo.value = (rule && rule.memo) || d.memo || d.usage || d.opAccName || ''
  // 命中规则的行,把规则里的分类路径展平送给 el-cascader
  if (rule && rule.catid && props.categories) {
    const allCats = []
      .concat(props.categories.payout || [])
      .concat(props.categories.income || [])
    for (const top of allCats) {
      const path = findCatPath(top, rule.catid)
      if (path) { catPath.value = path; break }
    }
  }
  saveRule.value = false
  conditions.value = presetConds(d).length ? presetConds(d) : [defaultCond()]
})

const catOptions = computed(() => {
  const c = props.categories || {}
  return op.value === 'income' ? (c.income || []) : (c.payout || [])
})

async function submit() {
  if (op.value === 'transfer' && !opSuiid.value) {
    ElMessage.warning('请选择对手账户')
    return
  }
  if (op.value !== 'transfer' && !catPath.value.length) {
    ElMessage.warning('请选择分类')
    return
  }
  // 存为规则时校验至少一条非空条件 —— 后端也会校验,前端先报更友好
  let condsToSave = null
  if (saveRule.value) {
    const list = conditions.value
      .map(c => ({ field: c.field, match: c.match, value: (c.value || '').toString().trim() }))
      .filter(c => c.value)
    if (!list.length) {
      ElMessage.warning('至少要有一条匹配条件')
      return
    }
    condsToSave = list
  }
  loading.value = true
  try {
    await emit('submit', {
      op: op.value,
      catid: op.value === 'transfer' ? null : catPath.value[catPath.value.length - 1],
      opSuiid: op.value === 'transfer' ? opSuiid.value : null,
      memo: memo.value,
      saveRule: saveRule.value,
      conditions: condsToSave,
      // 命中规则记账时,把规则 id 回传给后端,后端累加命中次数
      ruleId: props.preselectRule ? props.preselectRule.id : null
    })
    emit('update:modelValue', false)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.amount {
  font-size: 17px;
  font-weight: 500;
}
.ellipsis {
  display: inline-block;
  max-width: 480px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.conds {
  width: 100%;
}
.cond-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}
.tip {
  font-size: 12px;
  color: #909399;
  margin-top: 6px;
}
</style>
