<template>
  <div class="bills">
    <div class="top-bar">
      <div>
        <span class="book-name">{{ state.bookName || '账本' }}</span>
        <el-select v-model="state.suiid" placeholder="选择记账账户" style="width:220px;margin-left:16px"
                   @change="onAccountChange">
          <el-option v-for="a in state.accounts" :key="a.id"
                     :label="a.group ? `${a.name}（${a.group}）` : a.name" :value="a.id" />
        </el-select>
      </div>
      <div class="actions">
        <el-button link @click="emit('open-rules')">自动记账规则</el-button>
        <el-button link @click="emit('switch-book')">切换账本</el-button>
        <el-button link @click="emit('logout')">退出</el-button>
      </div>
    </div>

    <el-card class="import-card">
      <el-tabs v-model="tab">
        <el-tab-pane label="上传账单" name="upload">
          <div class="upload-row">
            <span class="lbl">账单类型</span>
            <el-select v-model="bankType" placeholder="请选择" style="width:240px"
                       :disabled="!billReaders.length">
              <el-option v-for="r in billReaders" :key="r.type"
                         :label="r.label" :value="r.type" />
            </el-select>
          </div>
          <el-upload :auto-upload="false" :show-file-list="true" :limit="1"
                     accept=".xlsx,.xls" :on-change="onFileChange" :on-remove="() => file = null">
            <el-button :disabled="!bankType">选择账单文件</el-button>
            <template #tip>
              <div class="tip">先选类型再选文件；解析时会把类型传给后端，不再看文件名</div>
            </template>
          </el-upload>
          <el-button type="primary" style="margin-top:12px" :loading="loading"
                     :disabled="!file || !bankType" @click="doUpload">解析账单</el-button>
        </el-tab-pane>

        <el-tab-pane label="Gmail 账单" name="gmail">
          <div class="gmail-bar">
            <el-tag :type="gmailOk ? 'success' : 'info'">
              {{ gmailOk ? '已授权（保存在本机）' : '未授权' }}
            </el-tag>
            <el-button size="small" @click="gmailAuth">授权 / 重新授权</el-button>
            <el-button size="small" :disabled="!gmailOk" :loading="loading"
                       @click="loadMails">读取账单邮件</el-button>
            <el-button size="small" type="primary" :disabled="!selectedMails.length"
                       :loading="loading" @click="loadSelected">加载所选</el-button>
            <el-button size="small" type="danger" plain :disabled="!gmailOk"
                       @click="gmailRevoke">删除授权</el-button>
          </div>
          <el-table v-if="mails.length" :data="mails" size="small" style="margin-top:12px"
                    @selection-change="s => selectedMails = s">
            <el-table-column type="selection" width="46" />
            <el-table-column prop="date" label="日期" width="110" />
            <el-table-column prop="subject" label="主题" show-overflow-tooltip />
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <el-card v-if="state.bills.length" class="list-card">
      <div class="list-header">
        <div>
          <span>卡号 {{ state.bankno }}</span>
          <span class="stat">共 {{ state.bills.length }} 条 ·
            已入账 {{ countBy('matched') }} · 待处理 {{ state.bills.length - countBy('matched') }}</span>
        </div>
        <el-button size="small" type="primary" :disabled="!countBy('auto')" :loading="loading"
                   @click="autoTallyAll">一键按规则记账（{{ countBy('auto') }} 条）</el-button>
      </div>

      <el-table :data="state.bills" size="small" stripe>
        <el-table-column label="日期" width="100">
          <template #default="{ row }">{{ formatDate(row.date) }}</template>
        </el-table-column>
        <el-table-column label="金额" width="100" align="right">
          <template #default="{ row }">
            <span :class="row.transType === 'income' ? 'amt-in' : 'amt-out'">
              {{ row.transType === 'income' ? '+' : '-' }}{{ row.amount }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="opAccName" label="对手" width="160" show-overflow-tooltip />
        <el-table-column prop="usage" label="用途" width="140" show-overflow-tooltip />
        <el-table-column prop="memo" label="备注" min-width="140" show-overflow-tooltip />
        <el-table-column label="状态" width="150">
          <template #default="{ row }">
            <el-tag v-if="row.status === 'matched'" type="success" size="small">
              已入账
            </el-tag>
            <el-tag v-else-if="row.status === 'auto'" type="warning" size="small">
              规则可自动
            </el-tag>
            <el-tag v-else type="info" size="small">待记账</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="账本记录" width="200">
          <template #default="{ row }">
            <!--
              悬停展开,展示账本里的全貌(分类、对方账户、备注、时间)。
              触发方式用 hover —— 鼠标经过就浮起来,比对账时的快速核对够用。
            -->
            <el-popover v-if="row.matched"
                        placement="left-start" trigger="hover"
                        :width="340" :show-arrow="true">
              <template #reference>
                <span class="matched-info link">{{ typeName(row.matched.tranType) }}
                  {{ row.matched.itemAmount }}</span>
              </template>
              <MatchedRecord :matched="row.matched" />
            </el-popover>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="90">
          <template #default="{ row, $index }">
            <el-button link type="primary" :disabled="row.status === 'matched'"
                       @click="openTally(row, $index)">记账</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <TallyDialog v-model="dialogVisible" :detail="currentDetail" :accounts="state.accounts"
                 :categories="state.categories" :preselect-rule="currentRule"
                 @submit="doTally" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import TallyDialog from '../components/TallyDialog.vue'
import MatchedRecord from '../components/MatchedRecord.vue'
import { state, api, formatDate, getGmailCreds, saveGmailCreds, clearGmailCreds } from '../api.js'

const emit = defineEmits(['logout', 'switch-book', 'open-rules'])

const tab = ref('upload')
const file = ref(null)
const loading = ref(false)
const mails = ref([])
const selectedMails = ref([])
// 凭据存在共享 state 里: 授权回调后父组件领取凭据,这里会自动更新
const gmailOk = computed(() => !!state.gmailCreds)
const dialogVisible = ref(false)
const currentDetail = ref(null)
const currentIndex = ref(-1)
const currentRule = ref(null)

// 用户在页面上选择的账单类型。空表示还没选 —— 文件按钮与解析按钮都被禁。
const bankType = ref('')
// 后端返回的白名单[{type, label}],进入页面一次性拉,只读不写
const billReaders = ref([])

onMounted(async () => {
  if (!state.accounts.length) {
    const r = await api.accounts(state.sid)
    state.accounts = r.accounts
  }
  if (!state.categories.payout.length) {
    const r = await api.categories(state.sid)
    state.categories = r.categories
  }
  // 拉后端白名单。失败也不阻塞 —— 至少留一个空下拉提示用户。
  try {
    const r = await api.listBillReaders()
    billReaders.value = r.readers || []
    if (!bankType.value && billReaders.value.length) bankType.value = billReaders.value[0].type
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '无法读取账单类型列表')
  }
})

function onFileChange(uploadFile) {
  file.value = uploadFile.raw
}

async function doUpload() {
  loading.value = true
  try {
    const r = await api.upload(state.sid, file.value, bankType.value)
    state.bankno = r.bankno
    state.bills = r.details.map(d => ({ ...d, status: 'pending' }))
    state.source = 'upload'
    if (r.suiid) {
      state.suiid = r.suiid
      await doReconcile()
    } else {
      ElMessage.warning('该卡号还没有配置账户映射，请在上方选择记账账户')
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '解析失败')
  } finally {
    loading.value = false
  }
}

async function doReconcile() {
  loading.value = true
  try {
    const r = await api.reconcile(state.sid, state.suiid)
    state.bills = r.items
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '对账失败')
  } finally {
    loading.value = false
  }
}

function onAccountChange() {
  if (state.bills.length) doReconcile()
}

function countBy(status) {
  return state.bills.filter(b => b.status === status).length
}

function typeName(t) {
  return { 1: '支出', 2: '转账', 5: '收入' }[t] || '-'
}

function openTally(row, index) {
  currentDetail.value = row
  currentIndex.value = index
  // 规则命中的预填规则里的分类,并记住规则 id —— 真正记账时回传累加命中次数
  if (row.rule) {
    row.ruleCatid = row.rule.catid
    currentRule.value = row.rule
  } else {
    currentRule.value = null
  }
  dialogVisible.value = true
}

async function doTally(payload) {
  try {
    await api.tally({
      sid: state.sid,
      suiid: state.suiid,
      index: currentIndex.value,
      ...payload
    })
    ElMessage.success('记账成功')
    await doReconcile()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '记账失败')
  }
}

async function autoTallyAll() {
  loading.value = true
  let n = 0
  try {
    for (let i = 0; i < state.bills.length; i++) {
      const b = state.bills[i]
      if (b.status !== 'auto' || !b.rule) continue
      await api.tally({
        sid: state.sid,
        suiid: state.suiid,
        index: i,
        op: b.rule.op,
        catid: b.rule.catid || null,
        opSuiid: b.rule.opSuiid || null,
        memo: b.rule.memo || b.memo || '',
        ruleId: b.rule.id  // 让后端累加这条规则的命中次数
      })
      n++
    }
    ElMessage.success(`已自动记账 ${n} 条`)
    await doReconcile()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '自动记账中断')
    await doReconcile()
  } finally {
    loading.value = false
  }
}

async function gmailAuth() {
  try {
    const r = await api.gmailAuthUrl(state.sid)
    window.location.href = r.url
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '未配置 Google OAuth')
  }
}

async function loadMails() {
  loading.value = true
  try {
    const r = await api.gmailMails(state.sid, getGmailCreds())
    saveGmailCreds(r.creds)
    mails.value = r.mails
    if (!r.mails.length) ElMessage.info('没有找到账单邮件')
  } catch (e) {
    handleGmailError(e, '读取邮件失败')
  } finally {
    loading.value = false
  }
}

// 401 表示 refresh_token 已失效(被撤销/过期),此时本地凭据没用了,清掉并引导重授权
function handleGmailError(e, fallback) {
  if (e.response?.status === 401) {
    clearGmailCreds()
    mails.value = []
  }
  ElMessage.error(e.response?.data?.detail || fallback)
}

async function gmailRevoke() {
  clearGmailCreds()
  mails.value = []
  selectedMails.value = []
  ElMessage.success('已删除本机保存的 Gmail 授权')
}

async function loadSelected() {
  loading.value = true
  try {
    const r = await api.gmailLoad(state.sid, selectedMails.value.map(m => m.id),
                                  state.suiid, getGmailCreds())
    saveGmailCreds(r.creds)
    state.bankno = r.bankno
    state.bills = r.details.map(d => ({ ...d, status: 'pending' }))
    state.source = 'gmail'
    if (state.suiid) await doReconcile()
    else ElMessage.warning('请先选择记账账户')
  } catch (e) {
    handleGmailError(e, '加载失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.bills {
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
.book-name {
  font-size: 16px;
  font-weight: 500;
}
.actions {
  display: flex;
  align-items: center;
  gap: 4px;
}
.import-card {
  margin-bottom: 16px;
}
.tip {
  font-size: 12px;
  color: #909399;
}
.gmail-bar {
  display: flex;
  align-items: center;
  gap: 10px;
}
.upload-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.upload-row .lbl {
  font-size: 13px;
  color: #606266;
  width: 64px;
  text-align: right;
}
.list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  font-size: 13px;
}
.stat {
  margin-left: 12px;
  color: #606266;
}
.amt-in {
  color: #e24b4a;
}
.amt-out {
  color: #1d9e75;
}
.matched-info {
  color: #909399;
  font-size: 12px;
}
/* 账本记录有悬停弹窗 —— 给点视觉提示,鼠标移上去像可点 */
.matched-info.link {
  color: #409eff;
  cursor: help;
  border-bottom: 1px dashed rgba(64, 158, 255, 0.5);
}
</style>
