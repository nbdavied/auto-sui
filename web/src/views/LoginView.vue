<template>
  <div class="login-page">
    <el-card class="login-card">
      <h2>auto-sui 账单对账</h2>

      <el-form v-if="!state.books.length" @submit.prevent>
        <el-form-item label="随手记账号">
          <el-input v-model="username" placeholder="注册邮箱" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="password" type="password" show-password
                    placeholder="随手记密码" @keyup.enter="doLogin" />
        </el-form-item>
        <el-checkbox v-model="remember">在本机保存账号密码</el-checkbox>
        <div class="tip">
          凭据只保存在这台电脑的浏览器里，不会上传到服务器。
        </div>
        <el-button type="primary" :loading="loading" style="width:100%;margin-top:12px"
                   @click="doLogin">登录</el-button>
      </el-form>

      <div v-else>
        <div class="section-title">选择账本</div>
        <el-radio-group v-model="picked" class="book-list">
          <el-radio v-for="b in state.books" :key="b.id" :value="b.id" class="book-item">
            {{ b.name }}
          </el-radio>
        </el-radio-group>
        <el-button type="primary" :loading="loading" style="width:100%;margin-top:16px"
                   :disabled="!picked" @click="doSelectBook">进入对账</el-button>
        <el-button link style="width:100%;margin-top:8px" @click="reset">换个账号</el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { state, api, saveLocal, clearLocal, isSelecting, setSelecting } from '../api.js'

const username = ref(state.username)
const password = ref(state.password)
const remember = ref(true)
const loading = ref(false)
const picked = ref('')

// 用户主动点了「切换账本」时,不要自动进入上次的账本,停在本页让他选
const forceSelect = ref(isSelecting())

onMounted(async () => {
  // 本地已保存凭据则静默重登,直接进上次选的账本
  if (state.username && state.password) {
    try {
      const r = await api.login(state.username, state.password)
      saveLocal({ sid: r.sid, username: state.username, password: state.password })
      state.books = r.books
      if (r.books.length === 1 && r.bookId) picked.value = r.bookId
      if (r.bookId && !forceSelect.value) await enterBook(r.bookId, true)
    } catch (e) {
      state.books = []
    }
  }
})

async function doLogin() {
  if (!username.value || !password.value) {
    ElMessage.warning('请输入账号和密码')
    return
  }
  loading.value = true
  try {
    const r = await api.login(username.value, password.value)
    saveLocal({
      sid: r.sid,
      username: remember.value ? username.value : '',
      password: remember.value ? password.value : ''
    })
    state.books = r.books
    if (r.books.length === 1) picked.value = r.books[0].id
    if (r.bookId && !forceSelect.value) await enterBook(r.bookId, true)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '登录失败')
  } finally {
    loading.value = false
  }
}

async function enterBook(bookId, silent = false) {
  const r = await api.selectBook(state.sid, bookId)
  const book = state.books.find(b => b.id === bookId)
  saveLocal({ bookId, bookName: book ? book.name : '' })
  setSelecting(false)
  state.accounts = r.accounts
  state.categories = r.categories
  if (!silent) ElMessage.success('已进入账本')
}

async function doSelectBook() {
  loading.value = true
  try {
    await enterBook(picked.value)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '切换账本失败')
  } finally {
    loading.value = false
  }
}

function reset() {
  clearLocal()
  state.books = []
  username.value = ''
  password.value = ''
}
</script>

<style scoped>
.login-page {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
}
.login-card {
  width: 420px;
}
h2 {
  margin: 0 0 20px;
  font-size: 19px;
  font-weight: 500;
}
.tip {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
  line-height: 1.6;
}
.section-title {
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 500;
}
.book-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.book-item {
  margin-right: 0;
}
</style>
