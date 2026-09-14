<template>
  <div class="rules">
    <div class="top-bar">
      <span class="title">自动记账规则</span>
      <div class="actions">
        <el-button link @click="emit('back')">返回对账</el-button>
      </div>
    </div>

    <el-card>
      <div class="list-header">
        <div class="stat">
          共 {{ rules.length }} 条，命中 {{ hitRules }} 条从未命中
          <el-tag v-if="hitRules" type="success" size="small">有效</el-tag>
        </div>
        <el-button type="primary" :icon="Plus" @click="openEdit(null)">新增规则</el-button>
      </div>

      <el-table :data="rules" size="small" stripe :empty-text="'还没有规则，去记账时点「存为规则」即可生成'">
        <el-table-column label="优先级" width="80" align="center">
          <template #default="{ row }">
            <el-input-number v-model="row.priority" size="small" :min="0" :step="10"
                             controls-position="right"
                             @change="onPriorityChange(row)" />
          </template>
        </el-table-column>
        <el-table-column label="匹配条件" min-width="280">
          <template #default="{ row }">
            <div class="conds">
              <el-tag v-for="(c, i) in parseConds(row.conditions)" :key="i"
                      size="small" :type="i === 0 ? '' : 'info'" effect="plain"
                      style="margin: 2px 4px 2px 0;">
                {{ condLabel(c) }}
              </el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="记账方式" width="90">
          <template #default="{ row }">
            {{ opLabel(row.op) }}
          </template>
        </el-table-column>
        <el-table-column label="分类 / 对手" width="160" show-overflow-tooltip>
          <template #default="{ row }">
            {{ catLabel(row) }}
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="120" show-overflow-tooltip
                         prop="memo" />
        <el-table-column label="命中" width="100" align="center">
          <template #default="{ row }">
            <el-tooltip v-if="row.last_hit" :content="'上次命中: ' + formatDateTime(row.last_hit)">
              <el-tag size="small">{{ row.hit_count }} 次</el-tag>
            </el-tooltip>
            <span v-else class="muted">未命中</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="130">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-popconfirm title="确定删除这条规则？" @confirm="onDelete(row)">
              <template #reference>
                <el-button link type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 编辑弹窗 -->
    <el-dialog v-model="editVisible" :title="form.id ? '编辑规则' : '新增规则'" width="640px">
      <el-form label-width="88px">
        <el-form-item label="匹配条件">
          <div class="conds-edit">
            <div v-for="(c, i) in form.conditions" :key="i" class="cond-row">
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
                         v-model="c.value" size="small" style="width:120px">
                <el-option label="收入" value="income" />
                <el-option label="支出" value="payout" />
              </el-select>
              <el-input v-else v-model="c.value" size="small" style="width:180px" />
              <el-button link type="danger"
                         :disabled="form.conditions.length === 1"
                         @click="form.conditions.splice(i, 1)">删除</el-button>
            </div>
            <el-button link type="primary" @click="form.conditions.push(defaultCond())">+ 添加条件</el-button>
          </div>
        </el-form-item>

        <el-form-item label="记账方式">
          <el-radio-group v-model="form.op">
            <el-radio-button value="payout">支出</el-radio-button>
            <el-radio-button value="income">收入</el-radio-button>
            <el-radio-button value="transfer">转账</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="form.op === 'transfer'" label="对手账户">
          <el-select v-model="form.opSuiid" placeholder="选择对手账户" style="width:100%">
            <el-option v-for="a in accounts" :key="a.id" :label="a.name" :value="a.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-else label="分类">
          <el-cascader v-model="formCatPath" :options="catOptions" style="width:100%"
                       :props="{ value: 'id', label: 'name', children: 'children', emitPath: true }" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.memo" />
        </el-form-item>
        <el-form-item label="优先级">
          <el-input-number v-model="form.priority" :min="0" :step="10" />
          <span class="tip">值越大越先匹配</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { api, state } from '../api.js'

const emit = defineEmits(['back'])

const rules = ref([])
const accounts = ref([])
const categories = ref({ income: [], payout: [] })
const editVisible = ref(false)
const saving = ref(false)
const form = ref(newForm())
const formCatPath = ref([])

function newForm() {
  return { id: null, conditions: [defaultCond()], op: 'payout',
           catid: '', opSuiid: '', memo: '', priority: 0 }
}

function defaultCond() {
  return { field: 'opAccName', match: 'eq', value: '' }
}

const NUMERIC_FIELDS = new Set(['amount'])
function availableMatches(c) {
  if (NUMERIC_FIELDS.has(c.field)) {
    return [{ value: 'eq', label: '等于' }, { value: 'gt', label: '大于' },
            { value: 'lt', label: '小于' }]
  }
  return api.ruleMatches
}
function onFieldChange(c) {
  const valid = availableMatches(c).some(m => m.value === c.match)
  if (!valid) c.match = NUMERIC_FIELDS.has(c.field) ? 'eq' : 'contains'
}

const catOptions = computed(() => {
  return form.value.op === 'income'
    ? (categories.value.income || [])
    : (categories.value.payout || [])
})

const hitRules = computed(() => rules.value.filter(r => r.hit_count > 0).length)

onMounted(async () => {
  await Promise.all([loadRules(), loadAccounts(), loadCategories()])
})

async function loadRules() {
  try {
    const r = await api.rules.list(state.sid)
    // 给编辑表格留可写的副本 —— 直接绑定 v-model 在 ref 数组上 Vue 会自动响应
    rules.value = (r.rules || []).map(x => ({ ...x, conditions: x.conditions }))
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载规则失败')
  }
}

async function loadAccounts() {
  if (state.accounts.length) {
    accounts.value = state.accounts
    return
  }
  try {
    const r = await api.accounts(state.sid)
    state.accounts = r.accounts
    accounts.value = r.accounts
  } catch (e) {
    // 忽略: 编辑规则不需要账户也能展示列表
  }
}

async function loadCategories() {
  if (state.categories.payout.length || state.categories.income.length) {
    categories.value = state.categories
    return
  }
  try {
    const r = await api.categories(state.sid)
    state.categories = r.categories
    categories.value = r.categories
  } catch (e) { /* 同上 */ }
}

function parseConds(raw) {
  if (Array.isArray(raw)) return raw
  if (!raw) return []
  try { return JSON.parse(raw) } catch (e) { return [] }
}

function fieldLabel(v) {
  const f = api.ruleFields.find(x => x.value === v)
  return f ? f.label : v
}
function matchLabel(v) {
  const m = api.ruleMatches.find(x => x.value === v)
  return m ? m.label : v
}
function condLabel(c) {
  return `${fieldLabel(c.field)} ${matchLabel(c.match)} "${c.value}"`
}

function opLabel(op) {
  return { payout: '支出', income: '收入', transfer: '转账' }[op] || op
}

// 根据 catid 在分类树里查中文名;查不到就显示 id
function findCatName(cats, target) {
  for (const t of cats) {
    if (t.id === target) return t.name
    if (t.children) {
      const sub = findCatName(t.children, target)
      if (sub) return sub
    }
  }
  return null
}
function catLabel(row) {
  if (row.op === 'transfer') {
    const a = accounts.value.find(x => x.id === row.opSuiid)
    return a ? `→ ${a.name}` : row.opSuiid ? `→ ${row.opSuiid}` : '未设对手'
  }
  const all = [].concat(categories.value.payout || [])
              .concat(categories.value.income || [])
  const name = findCatName(all, row.catid)
  return name || row.catid || '未设分类'
}

function formatDateTime(s) {
  if (!s) return ''
  return s.replace('T', ' ').slice(0, 16)
}

function findCatPath(node, target) {
  if (node.id === target) return [node.id]
  if (!node.children) return null
  for (const c of node.children) {
    const sub = findCatPath(c, target)
    if (sub) return [node.id, ...sub]
  }
  return null
}

async function onPriorityChange(row) {
  // el-input-number 失焦或按下箭头时保存;避免每次按键都打接口
  try {
    await api.rules.update(row.id, { sid: state.sid, priority: row.priority })
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存优先级失败')
  }
}

function openEdit(row) {
  if (!row) {
    form.value = newForm()
    formCatPath.value = []
    editVisible.value = true
    return
  }
  const conds = parseConds(row.conditions)
  form.value = {
    id: row.id,
    conditions: conds.length ? conds : [defaultCond()],
    op: row.op || 'payout',
    catid: row.catid || '',
    opSuiid: row.opSuiid || '',
    memo: row.memo || '',
    priority: row.priority || 0
  }
  // 把 catid 翻译成分类路径
  if (row.catid) {
    const all = [].concat(categories.value.payout || [])
                .concat(categories.value.income || [])
    for (const top of all) {
      const p = findCatPath(top, row.catid)
      if (p) { formCatPath.value = p; break }
    }
  } else {
    formCatPath.value = []
  }
  editVisible.value = true
}

async function onSave() {
  const list = form.value.conditions
    .map(c => ({ field: c.field, match: c.match, value: (c.value || '').toString().trim() }))
    .filter(c => c.value)
  if (!list.length) { ElMessage.warning('请至少填一条匹配条件'); return }
  if (form.value.op === 'transfer' && !form.value.opSuiid) {
    ElMessage.warning('请选择对手账户'); return
  }
  if (form.value.op !== 'transfer' && !formCatPath.value.length) {
    ElMessage.warning('请选择分类'); return
  }
  const catid = form.value.op === 'transfer'
    ? ''
    : formCatPath.value[formCatPath.value.length - 1]
  saving.value = true
  try {
    const payload = {
      sid: state.sid,
      conditions: list,
      op: form.value.op,
      priority: form.value.priority,
      memo: form.value.memo || null,
      catid: catid || null,
      opSuiid: form.value.op === 'transfer' ? form.value.opSuiid : null
    }
    if (form.value.id) {
      await api.rules.update(form.value.id, payload)
      ElMessage.success('已保存')
    } else {
      await api.rules.add(payload)
      ElMessage.success('已新增')
    }
    editVisible.value = false
    await loadRules()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function onDelete(row) {
  try {
    await api.rules.remove(state.sid, row.id)
    ElMessage.success('已删除')
    await loadRules()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}
</script>

<style scoped>
.rules {
  max-width: 1180px;
  margin: 0 auto;
  padding: 20px 16px 40px;
}
.top-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.title {
  font-size: 16px;
  font-weight: 500;
}
.list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.stat {
  font-size: 13px;
  color: #606266;
}
.muted {
  color: #c0c4cc;
}
.conds {
  line-height: 1.6;
}
.conds-edit {
  width: 100%;
}
.cond-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}
.tip {
  margin-left: 12px;
  font-size: 12px;
  color: #909399;
}
</style>
