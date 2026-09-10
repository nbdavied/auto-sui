<template>
  <div class="app">
    <LoginView v-if="!state.bookId" @logged-in="onLoggedIn" />
    <BillsView v-else @logout="onLogout" @switch-book="onSwitchBook" />
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import LoginView from './views/LoginView.vue'
import BillsView from './views/BillsView.vue'
import { state, api, saveLocal, clearLocal, leaveBook } from './api.js'

// Gmail OAuth 回调会带 ?gmail=ok&sid=xxx 回到前端
onMounted(() => {
  const params = new URLSearchParams(window.location.search)
  if (params.get('gmail')) {
    const sid = params.get('sid')
    if (sid) saveLocal({ sid })
    const result = params.get('gmail')
    if (result === 'ok') ElMessage.success('Gmail 授权成功')
    else if (result === 'expired') ElMessage.warning('会话已过期，请重新登录')
    else ElMessage.error('Gmail 授权失败')
    window.history.replaceState({}, '', window.location.pathname)
  }
})

function onLoggedIn() {}

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
