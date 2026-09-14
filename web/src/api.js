import axios from 'axios'
import { reactive } from 'vue'

// 凭据保存在浏览器本地: 服务端不存密码,刷新页面后可用本地凭据自动重登
const KEY = {
  sid: 'autosui.sid',
  username: 'autosui.username',
  password: 'autosui.password',
  bookId: 'autosui.bookId',
  bookName: 'autosui.bookName',
  selecting: 'autosui.selecting',
  gmailCreds: 'autosui.gmailCreds'
}

// 持久化当前视图(对账 / 规则),刷新页面后还能停在原处
const VIEW_KEY = 'autosui.view'

// Gmail OAuth 凭据存在浏览器本地,目的就是「一次授权长期有效」。
// 因此退出登录/切换账本都不清除它,只有用户点「删除授权」才清。
//
// 放进 reactive state 而不只是 localStorage: 授权回调回来时子组件会先于父组件
// 挂载(父组件才负责领取凭据),读 localStorage 会拿到旧值而误显示「未授权」。
export function getGmailCreds() {
  return localStorage.getItem(KEY.gmailCreds) || ''
}

export function saveGmailCreds(json) {
  if (!json) return
  localStorage.setItem(KEY.gmailCreds, json)
  state.gmailCreds = json
}

export function clearGmailCreds() {
  localStorage.removeItem(KEY.gmailCreds)
  state.gmailCreds = ''
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

export function setView(v) {
  if (v) localStorage.setItem(VIEW_KEY, v)
  else localStorage.removeItem(VIEW_KEY)
  state.view = v
}
export function getView() {
  return localStorage.getItem(VIEW_KEY) || ''
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
  source: '',
  gmailCreds: localStorage.getItem(KEY.gmailCreds) || '',
  view: localStorage.getItem(VIEW_KEY) || '',
  // 主会话失效标记: expireSession() 置位,LoginView 挂载后据此提示「登录已过期」。
  // 仅作前端提示用,不持久化。
  sessionExpired: false
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
  Object.entries(KEY).forEach(([name, k]) => {
    // Gmail 凭据跨登录保留,避免退出后又要重新授权。
    // 注意比较的是「KEY 的名字」而不是「KEY 的值」—— 之前写成 k === KEY.gmailCreds,
    // 拿 localStorage 的 key 字符串去比 'autosui.gmailCreds' 永远不等,
    // 于是退出登录时 Gmail 凭据也被清掉了(表现为「之前正常,现在又要重新授权」)。
    if (name === 'gmailCreds') return
    localStorage.removeItem(k)
  })
  localStorage.removeItem(VIEW_KEY)
  state.sid = ''
  state.bookId = ''
  state.bookName = ''
  state.books = []
  state.bills = []
  state.view = ''
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
  // 离开账本时也回到对账页,顺便清掉规则页标记
  state.view = ''
}

const http = axios.create({ baseURL: '/api', timeout: 60000 })

// 主会话失效: 清掉「会话态 + 当前账本」,但保留账号密码(供 LoginView 自动重登)
// 与 Gmail 凭据(跨登录保留),让 App 切回 LoginView。
// 注意: 不能用 clearLocal() —— 它会把账号密码和 Gmail 凭据也一起清掉,
// 那样退出后又要重新输密码 / 重新授权。
function expireSession() {
  state.sessionExpired = true
  state.sid = ''
  state.bookId = ''
  state.bookName = ''
  localStorage.removeItem(KEY.sid)
  localStorage.removeItem(KEY.bookId)
  localStorage.removeItem(KEY.bookName)
}

http.interceptors.response.use(
  res => res.data,
  err => {
    if (err.response && err.response.status === 401) {
      const detail = (err.response.data && err.response.data.detail) || ''
      // Gmail 授权相关的 401(未授权 / refresh_token 失效)由 BillsView.handleGmailError
      // 处理(只清 Gmail 凭据、提示重新授权)。这里只认「主会话失效」,把 bookId 也
      // 清掉,App 才会切回 LoginView;若 detail 含 "Gmail" 说明是 Gmail 凭据问题,
      // 不是主会话失效,不能把用户踢下线。
      //
      // 之前只清了 state.sid 却没清 state.bookId: App 一直按 bookId 显示对账页,
      // 请求反复 401,卡在「看得见账本页却一直在报错」的状态,刷新也不会回到登录页。
      if (!detail.includes('Gmail')) {
        expireSession()
      }
    }
    return Promise.reject(err)
  }
)

export const api = {
  login(username, password, shenxiangToken = '') {
    // shenxiangToken 可选:服务端风控给密码登录塞图形码时(code 4099),
    // 用浏览器会话里已有的 access_token 绕过,省掉验证码流程。
    return http.post('/login', { username, password, shenxiangToken })
  },
  selectBook(sid, bookId, provider = '') {
    return http.post('/book', { sid, bookId, provider })
  },
  accounts(sid) {
    return http.get('/accounts', { params: { sid } })
  },
  categories(sid) {
    return http.get('/categories', { params: { sid } })
  },
  upload(sid, file, bankType) {
    const form = new FormData()
    form.append('sid', sid)
    form.append('bankType', bankType)
    form.append('file', file)
    return http.post('/bills/upload', form)
  },
  // 后端白名单: 上传路径支持的账单类型(abc/ccb/...)。前端下拉数据源。
  listBillReaders() {
    return http.get('/bills/readers')
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
  // 授权完成后把凭据从后端领回,存到浏览器
  gmailClaim(sid) {
    return http.post('/gmail/claim', { sid })
  },
  gmailMails(sid, creds, maxResults = 30) {
    return http.post('/gmail/mails', { sid, creds, maxResults })
  },
  gmailLoad(sid, messageIds, suiid, creds) {
    return http.post('/gmail/load', { sid, messageIds, suiid, creds })
  },
  gmailArchive(sid, messageIds, creds) {
    return http.post('/gmail/archive', { sid, messageIds, creds })
  },

  // ----- 规则 -----
  // 前端使用的字段与匹配方式白名单，与后端 MATCH_FIELDS / MATCH_KINDS 一致。
  // 前端不存多份常量,直接放在这里方便编辑弹窗引用。
  ruleFields: [
    { value: 'opAccName', label: '对手户名' },
    { value: 'opAccNo',   label: '对手账号' },
    { value: 'memo',      label: '备注' },
    { value: 'usage',     label: '用途' },
    { value: 'amount',    label: '金额' },
    { value: 'transType', label: '收支方向' }
  ],
  ruleMatches: [
    { value: 'eq',         label: '等于' },
    { value: 'contains',   label: '包含' },
    { value: 'startswith', label: '开头是' },
    { value: 'regex',      label: '正则' },
    { value: 'gt',         label: '大于' },
    { value: 'lt',         label: '小于' }
  ],
  rules: {
    list(sid) {
      return http.get('/rules', { params: { sid } })
    },
    add(rule) {
      return http.post('/rules', rule)
    },
    update(id, patch) {
      return http.put(`/rules/${id}`, patch)
    },
    remove(sid, id) {
      return http.delete(`/rules/${id}`, { params: { sid } })
    }
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
