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

        <!--
          服务端风控会给密码登录塞图形验证码(code 4099)。浏览器会话里那颗
          access_token 仍然有效,填进来可以直接接管,不用做验证码流程。
        -->
        <div class="token-section">
          <el-button link type="primary" @click="showToken = !showToken">
            {{ showToken ? '收起' : '密码登录失败？用 access_token 登录' }}
          </el-button>
          <div v-if="showToken" class="token-box">
            <ol class="token-steps">
              <li>浏览器打开并登录
                <el-link type="primary" href="https://www.feidee.com/cloud/"
                         target="_blank">神象云网页版</el-link>
              </li>
              <li>按 F12 打开控制台，粘贴下面这行回车：</li>
            </ol>
            <div class="cmd" @click="copyCmd">
              <code>copy(localStorage.Authorization)</code>
              <span class="copy-hint">{{ copied ? '已复制' : '点击复制' }}</span>
            </div>
            <div class="token-steps">最后把结果粘贴到下面：</div>
            <el-input v-model="shenxiangToken" type="textarea" :rows="3"
                      placeholder="粘贴 access_token" />
          </div>
        </div>
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

// 图形验证码旁路:浏览器登录态里扒出来的神象云 access_token
const showToken = ref(false)
const shenxiangToken = ref('')
const copied = ref(false)

async function copyCmd() {
  try {
    await navigator.clipboard.writeText('copy(localStorage.Authorization)')
    copied.value = true
    setTimeout(() => { copied.value = false }, 1500)
  } catch (e) {
    ElMessage.warning('复制失败,请手动选中下方命令')
  }
}

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
  // 主会话刚过期被踢回登录页: 若本地没有可自动重登的账号密码,给个明确提示。
  // (能自动重登的话会自动跳回对账页,不必提示。)
  if (state.sessionExpired) {
    state.sessionExpired = false
    if (!state.books.length) {
      ElMessage.warning('登录状态已过期，请重新登录')
    }
  }
})

async function doLogin() {
  const tok = shenxiangToken.value.trim()
  // 有 token 时不需要密码 —— token 本身就代表已经登录过了
  if (!username.value || (!password.value && !tok)) {
    ElMessage.warning('请输入账号，以及密码或 access_token')
    return
  }
  loading.value = true
  try {
    const tok = shenxiangToken.value.trim()
    const r = await api.login(username.value, password.value, tok)
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
.token-section {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid #ebeef5;
  text-align: left;
}
.token-box {
  margin-top: 8px;
}
.token-steps {
  margin: 6px 0;
  padding-left: 18px;
  font-size: 12px;
  color: #606266;
  line-height: 1.8;
}
.cmd {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 7px 10px;
  background: #f5f7fa;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  cursor: pointer;
  margin-bottom: 8px;
}
.cmd code {
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
  color: #303133;
  word-break: break-all;
}
.copy-hint {
  flex-shrink: 0;
  font-size: 11px;
  color: #909399;
}
</style>
