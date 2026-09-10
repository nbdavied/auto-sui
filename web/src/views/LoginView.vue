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
        <!--
          同一账号可能同时拥有「神象云账本」与「旧随手记账本」。
          provider 标签告诉用户每个账本来自哪边,以免误以为是重复项。
        -->
        <el-radio-group v-model="picked" class="book-list">
          <el-radio v-for="b in state.books" :key="b.provider + ':' + b.id"
                    :value="b.provider + ':' + b.id" class="book-item">
            <span class="book-name">{{ b.name }}</span>
            <el-tag :type="b.provider === 'legacy' ? 'info' : 'success'"
                    size="small" effect="plain" class="book-tag">
              {{ providerLabel(b.provider) }}
            </el-tag>
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
// 账本选择:用 "provider:id" 拼接,同时携带来源,避免不同 provider 的 id 重叠
const picked = ref('')

const forceSelect = ref(isSelecting())

function providerLabel(p) {
  return p === 'legacy' ? '旧版' : '神象云'
}

// 把 "provider:id" 拆开,或仅按 id 查找
function findBook(token) {
  if (!token) return null
  if (token.includes(':')) {
    // 不限切分次数,保留所有 : 分隔的部分再重组
    const idx = token.indexOf(':')
    const p = token.slice(0, idx)
    const id = token.slice(idx + 1)
    return state.books.find(b => b.provider === p && b.id === id) || null
  }
  // 老格式(仅 id),兜底按 id 匹配,provider 取当时默认
  return state.books.find(b => b.id === token) || null
}

onMounted(async () => {
  if (state.username && state.password) {
    try {
      const r = await api.login(state.username, state.password)
      saveLocal({ sid: r.sid, username: state.username, password: state.password })
      state.books = r.books
      if (r.books.length === 1) {
        picked.value = r.books[0].provider + ':' + r.books[0].id
      }
      if (r.bookId && !forceSelect.value) {
        const target = state.books.find(b => b.id === r.bookId)
        await enterBook(target || state.books[0], true)
      }
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
    if (r.books.length === 1) {
      picked.value = r.books[0].provider + ':' + r.books[0].id
    }
    if (r.bookId && !forceSelect.value) {
      const target = state.books.find(b => b.id === r.bookId)
      await enterBook(target || state.books[0], true)
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '登录失败')
  } finally {
    loading.value = false
  }
}

async function enterBook(book, silent = false) {
  // book 可能是 {id, name, provider} 或单独一个 id 字符串
  const b = typeof book === 'string' ? findBook(book) : book
  if (!b) return
  // provider 必传 — 后端按它选 client
  const r = await api.selectBook(state.sid, b.id, b.provider)
  saveLocal({ bookId: b.id, bookName: b.name })
  setSelecting(false)
  state.accounts = r.accounts
  state.categories = r.categories
  if (!silent) ElMessage.success(`已进入账本 (${providerLabel(b.provider)})`)
}

async function doSelectBook() {
  loading.value = true
  try {
    const book = findBook(picked.value)
    if (!book) throw new Error('未选择账本')
    await enterBook(book)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || e.message || '切换账本失败')
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
  width: 460px;
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
  display: flex;
  align-items: center;
  gap: 8px;
}
.book-name {
  flex: 1;
}
.book-tag {
  margin-left: 4px;
}
</style>
