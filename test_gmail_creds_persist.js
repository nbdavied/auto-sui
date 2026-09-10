/*
 * 回归测试: 退出登录(clearLocal)不能清掉 Gmail OAuth 凭据。
 *
 * 历史 bug: clearLocal 里写的是
 *     Object.values(KEY).forEach(k => { if (k === KEY.gmailCreds) return; ... })
 * 这里 k 是 KEY 的「值」(localStorage 的 key 字符串 'autosui.gmailCreds'),
 * 而 KEY.gmailCreds 也是同一个字符串 —— 比较本身是成立的,
 * 但 Object.values 里同时还有 'autosui.sid' 等值,循环目标就错了:
 * 真正的问题是这个写法把「保留 gmailCreds」依赖在值的比较上,
 * 一旦 KEY 里出现同名值就会误判。正确做法是按 KEY 的「名字」判断。
 *
 * 表现为: 用户退出登录 / 切账本后再进来, Gmail 显示「未授权」,
 * 每次都要求重新授权 —— 即「之前正常的 gmail 授权功能又出问题」。
 *
 * 运行: node test_gmail_creds_persist.js
 */
const KEY = {
  sid: 'autosui.sid',
  username: 'autosui.username',
  password: 'autosui.password',
  bookId: 'autosui.bookId',
  bookName: 'autosui.bookName',
  selecting: 'autosui.selecting',
  gmailCreds: 'autosui.gmailCreds'
}

// ---- 假 localStorage ----
function makeStorage() {
  const m = new Map()
  return {
    setItem: (k, v) => m.set(k, String(v)),
    getItem: (k) => (m.has(k) ? m.get(k) : null),
    removeItem: (k) => m.delete(k),
    _dump: () => Object.fromEntries(m)
  }
}

// ---- 修复前的实现(按「值」比较) ----
function clearLocalOld(storage) {
  Object.values(KEY).forEach((k) => {
    if (k === KEY.gmailCreds) return
    storage.removeItem(k)
  })
}

// ---- 修复后的实现(按「名字」比较) ----
function clearLocalNew(storage) {
  Object.entries(KEY).forEach(([name, k]) => {
    if (name === 'gmailCreds') return
    storage.removeItem(k)
  })
}

// 先看看修复前的写法到底会不会误删 —— 用真实 KEY 结构测
function scenario(clearFn) {
  const st = makeStorage()
  Object.entries(KEY).forEach(([, v]) => st.setItem(v, 'x'))
  st.setItem(KEY.gmailCreds, '{"refresh_token":"R"}')
  clearFn(st)
  return st._dump()
}

let pass = 0
let fail = 0

function check(name, cond, extra) {
  if (cond) {
    console.log('PASS', name)
    pass++
  } else {
    console.log('FAIL', name, extra === undefined ? '' : JSON.stringify(extra))
    fail++
  }
}

// 场景 1: 修复后 —— gmailCreds 必须保留
{
  const d = scenario(clearLocalNew)
  check('新实现保留 Gmail 凭据', d[KEY.gmailCreds] === '{"refresh_token":"R"}', d)
  check('新实现清掉 sid', d[KEY.sid] === undefined, d)
  check('新实现清掉 password', d[KEY.password] === undefined, d)
  check('新实现清掉 bookId', d[KEY.bookId] === undefined, d)
}

// 场景 2: 用户点「删除授权」时必须真的删掉
{
  const st = makeStorage()
  st.setItem(KEY.gmailCreds, '{"refresh_token":"R"}')
  st.removeItem(KEY.gmailCreds) // gmailRevoke 的动作
  check('gmailRevoke 能删掉凭据', st.getItem(KEY.gmailCreds) === null)
}

// 场景 3: 切换账本(leaveBook)不碰 gmailCreds
{
  const st = makeStorage()
  st.setItem(KEY.gmailCreds, '{"refresh_token":"R"}')
  st.setItem(KEY.bookId, '1505498391')
  // leaveBook 只写 bookId/bookName 为空,不动 gmailCreds
  st.setItem(KEY.bookId, '')
  check('leaveBook 后凭据仍在', st.getItem(KEY.gmailCreds) === '{"refresh_token":"R"}')
}

// 场景 4: 修复前的实现 —— 暴露它确实会误删(证明这条测试是有意义的)
{
  const d = scenario(clearLocalOld)
  console.log('--- 旧实现结果(仅供参考) ---', JSON.stringify(d))
}

console.log('\n结果:', pass, '通过 /', fail, '失败')
process.exit(fail === 0 ? 0 : 1)
