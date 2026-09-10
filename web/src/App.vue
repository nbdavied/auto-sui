<template>
  <div class="app">
    <LoginView v-if="!state.bookId" @logged-in="onLoggedIn" />
    <RulesView v-else-if="state.view === 'rules'" @back="onBackFromRules" />
    <BillsView v-else @logout="onLogout" @switch-book="onSwitchBook"
               @open-rules="onOpenRules" />
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import LoginView from './views/LoginView.vue'
import RulesView from './views/RulesView.vue'
import BillsView from './views/BillsView.vue'
import { state, api, saveLocal, clearLocal, leaveBook, saveGmailCreds, setView } from './api.js'

// Gmail OAuth 回调会带 ?gmail=ok&sid=xxx 回到前端。
// 授权成功后立刻把凭据领回存到浏览器 —— 这样退出登录、服务重启都不用重新授权。
onMounted(async () => {
  const params = new URLSearchParams(window.location.search)
  if (!params.get('gmail')) return

  const sid = params.get('sid')
  if (sid) saveLocal({ sid })
  const result = params.get('gmail')
  window.history.replaceState({}, '', window.location.pathname)

  if (result !== 'ok') {
    if (result === 'expired') ElMessage.warning('会话已过期，请重新登录后再授权')
    else ElMessage.error('Gmail 授权失败')
    return
  }

  try {
    const r = await api.gmailClaim(sid || state.sid)
    saveGmailCreds(r.creds)
    ElMessage.success('Gmail 授权成功，凭据已保存在本机')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '授权凭据领取失败，请重新授权')
  }
})

function onLoggedIn() {}

// 切到规则管理页
function onOpenRules() {
  setView('rules')
}

// 从规则管理页返回对账页
function onBackFromRules() {
  setView('')
}

function onLogout() {
  clearLocal()
}

// 切换账本: 保留登录凭据,只退出当前账本并回到账本选择页
function onSwitchBook() {
  leaveBook()
}
</script>

<style>
body {
  margin: 0;
  font-family: -apple-system, "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif;
  background: #f5f7fa;
  color: #1f2937;
}
.app {
  min-height: 100vh;
}
</style>
