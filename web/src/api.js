import axios from 'axios'
import { reactive } from 'vue'

// 凭据保存在浏览器本地: 服务端不存密码,刷新页面后可用本地凭据自动重登
const KEY = {
  sid: 'autosui.sid',
  username: 'autosui.username',
  password: 'autosui.password',
  bookId: 'autosui.bookId',
  bookName: 'autosui.bookName',
  selecting: 'autosui.selecting'
}

// 用户主动「切换账本」时置位,选完账本清除。
// 持久化是为了刷新页面后仍然停在账本选择页,而不是被自动推进上次的账本。
export function setSelecting(v) {
  if (v) localStorage.setItem(KEY.selecting, '1')
  else localStorage.removeItem(KEY.selecting)
}

export function isSelecting() {
  return localStorage.getItem(KEY.selecting) === '1'
}

export const state = reactive({
  sid: localStorage.getItem(KEY.sid) || '',
  username: localStorage.getItem(KEY.username) || '',
  password: localStorage.getItem(KEY.password) || '',
  bookId: localStorage.getItem(KEY.bookId) || '',
  bookName: localStorage.getItem(KEY.bookName) || '',
  books: [],
  accounts: [],
  categories: { income: [], payout: [] },
  bills: [],
  bankno: '',
  suiid: '',
  source: ''
})

export function saveLocal(patch = {}) {
  Object.assign(state, patch)
  localStorage.setItem(KEY.sid, state.sid)
  localStorage.setItem(KEY.username, state.username)
  localStorage.setItem(KEY.password, state.password)
  localStorage.setItem(KEY.bookId, state.bookId)
  localStorage.setItem(KEY.bookName, state.bookName)
}

export function clearLocal() {
  Object.values(KEY).forEach(k => localStorage.removeItem(k))
  state.sid = ''
  state.bookId = ''
  state.bookName = ''
  state.books = []
  state.bills = []
}

// 切换账本: 只清账本相关的本地状态,保留登录凭据,免去重新输密码
export function leaveBook() {
  setSelecting(true)
  saveLocal({ bookId: '', bookName: '' })
  // 刻意不清 state.books: 保留列表,切回选择页时不会闪一下登录框,
  // LoginView 挂载后会重新拉取账本列表覆盖它
  state.bills = []
  state.suiid = ''
  state.accounts = []
  state.categories = { income: [], payout: [] }
}

const http = axios.create({ baseURL: '/api', timeout: 60000 })

http.interceptors.response.use(
  res => res.data,
  err => {
    if (err.response && err.response.status === 401) {
      state.sid = ''
    }
    return Promise.reject(err)
  }
)

export const api = {
  login(username, password) {
    return http.post('/login', { username, password })
  },
  selectBook(sid, bookId) {
    return http.post('/book', { sid, bookId })
  },
  accounts(sid) {
    return http.get('/accounts', { params: { sid } })
  },
  categories(sid) {
    return http.get('/categories', { params: { sid } })
  },
  upload(sid, file) {
    const form = new FormData()
    form.append('sid', sid)
    form.append('file', file)
    return http.post('/bills/upload', form)
  },
  reconcile(sid, suiid) {
    return http.post('/reconcile', { sid, suiid })
  },
  tally(payload) {
    return http.post('/tally', payload)
  },
  gmailStatus(sid) {
    return http.get('/gmail/status', { params: { sid } })
  },
  gmailAuthUrl(sid) {
    return http.get('/gmail/auth-url', { params: { sid } })
  },
  gmailMails(sid) {
    return http.get('/gmail/mails', { params: { sid } })
  },
  gmailLoad(sid, messageIds, suiid) {
    return http.post('/gmail/load', { sid, messageIds, suiid })
  }
}

export function parseAmount(v) {
  const n = parseFloat(v)
  return isNaN(n) ? 0 : n
}

export function formatDate(d) {
  if (!d || d.length !== 8) return d
  return `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}`
}

export function formatTime(t) {
  if (!t || t.length < 4) return ''
  return `${t.slice(0, 2)}:${t.slice(2, 4)}`
}
