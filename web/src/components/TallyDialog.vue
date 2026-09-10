<template>
  <el-dialog :model-value="modelValue" title="记账" width="520px"
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
        <el-input v-model="exp" type="textarea" :rows="2" placeholder="匹配表达式" />
        <div class="tip">
          可用变量：transType / amount / opAccNo / opAccName / usage / memo / suiid
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
import { formatDate, formatTime } from '../api.js'

const props = defineProps({
  modelValue: Boolean,
  detail: Object,
  accounts: Array,
  categories: Object
})
const emit = defineEmits(['update:modelValue', 'submit'])

const op = ref('payout')
const catPath = ref([])
const opSuiid = ref('')
const memo = ref('')
const saveRule = ref(false)
const exp = ref('')
const loading = ref(false)

watch(() => props.modelValue, (v) => {
  if (!v || !props.detail) return
  const d = props.detail
  op.value = d.transType === 'income' ? 'income' : 'payout'
  catPath.value = []
  opSuiid.value = ''
  memo.value = d.memo || d.usage || d.opAccName || ''
  saveRule.value = false
  exp.value = buildExp(d)
})

function buildExp(d) {
  const parts = [`transType == '${d.transType}'`]
  if (d.opAccNo) parts.push(`opAccNo == '${d.opAccNo}'`)
  else if (d.opAccName) parts.push(`opAccName == '${d.opAccName}'`)
  else if (d.memo) parts.push(`memo == '${d.memo}'`)
  return parts.join(' and ')
}

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
  loading.value = true
  try {
    await emit('submit', {
      op: op.value,
      catid: op.value === 'transfer' ? null : catPath.value[catPath.value.length - 1],
      opSuiid: op.value === 'transfer' ? opSuiid.value : null,
      memo: memo.value,
      saveRule: saveRule.value,
      exp: saveRule.value ? exp.value : null
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
  max-width: 360px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tip {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
</style>
