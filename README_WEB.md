# auto-sui Web 版使用说明

浏览器里完成「登录 → 导入账单 → 对账 → 记账」，支持多用户，各自用自己的随手记账号和 Gmail。

## 一、启动

### 0. 最省事的方式（Windows，推荐）

项目根目录放了两个批处理，双击即可：

| 文件 | 作用 |
|---|---|
| `start.bat` | 启动服务（约 3 秒后自动打开浏览器） |
| `stop.bat` | 停止服务（按端口找到监听进程并结束） |

想改端口 / 代理 / 是否热重载，用记事本打开 `start.bat`，改顶部这几行即可：

```bat
set "PORT=8000"
set "PROXY=socks5://127.0.0.1:10808"
set "RELOAD=0"
set "PY=C:\Users\nbdav\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
```

⚠️ **`RELOAD=1`（改代码自动重启）时不要做 Gmail 授权** —— 重启会打断 OAuth 回调，
导致 `?gmail=expired`。做授权请用 `RELOAD=0`。

### 1. 手动命令行启动（本机现有环境）

本项目当前使用工具链自带的 Python 3.13 环境，依赖已装好，**无需再 pip install**：

```bash
cd C:/Users/nbdav/projects/auto-sui

PYTHONIOENCODING=utf-8 \
HTTPS_PROXY=socks5://127.0.0.1:10808 \
HTTP_PROXY=socks5://127.0.0.1:10808 \
RELOAD=0 PORT=8000 \
"C:/Users/nbdav/.workbuddy/binaries/python/envs/default/Scripts/python.exe" run_server.py
```

启动后访问 <http://127.0.0.1:8000>，`Ctrl+C` 停止。

**环境变量说明**

| 变量 | 作用 | 不设会怎样 |
|---|---|---|
| `HTTPS_PROXY` / `HTTP_PROXY` | Google token 端点走代理 | Gmail 授权跳回 `?gmail=error`（境内连不上） |
| `RELOAD` | `1` = 改代码自动重启 | 默认 `1`；做 Gmail 授权时务必设 `0` |
| `PORT` | 监听端口 | 默认 `8000` |
| `AUTOSUI_SESSION_FILE` | 会话落盘路径 | `run_server.py` 默认设为 `sessions.db`；置空 = 纯内存 |
| `AUTOSUI_SESSION_TTL` | 会话有效期（秒） | 默认 8 小时 |
| `FRONTEND_URL` | 前端地址（开发模式） | 默认跳回当前域名 |

> 代理端口按你实际的来：Clash 常见 SOCKS5 `10808` / HTTP `10809`。
> 只用记账、不用 Gmail 的话，可以去掉两行 `PROXY`。

### 2. 停止服务

```bash
# 方式一：如果服务窗口还开着，直接在那个窗口按 Ctrl+C

# 方式二：按端口找进程结束（关掉了窗口 / 不确定 PID 时）
taskkill /F /PID <PID>          # PID 从下面这条命令拿
netstat -ano | findstr ":8000" | findstr "LISTENING"
```

> 注意用 `findstr "LISTENING"` 过滤。不加过滤时，已建立的连接对端也会显示 `:8000`
> （状态 `TIME_WAIT`、PID 为 `0`），照着那个 PID 杀是无效的。

### 3. 从零安装（换新机器时）

```bash
cd C:/Users/nbdav/projects/auto-sui

# 建虚拟环境（需 Python 3.11+，推荐 3.12/3.13）
python -m venv .venv

# 装后端依赖
.venv/Scripts/python.exe -m pip install --upgrade pip
.venv/Scripts/python.exe -m pip install -r requirements.txt

# 构建前端（需 Node 18+）
cd web
npm install
npm run build
cd ..

# 启动
.venv/Scripts/python.exe run_server.py
```

> ⚠️ 项目里已有的 `.venv` 是 Python **3.14**，缺 `fastapi` / `uvicorn`
> （仓库 `requirements.txt` 里的 Web 依赖当初没装进去）。**不要直接用它启动**，
> 否则报 `No module named 'fastapi'`。要么按上面第 3 节重建，要么补装：
> `.venv/Scripts/python.exe -m pip install -r requirements.txt`

### 4. 前端开发模式（改前端代码时）

生产模式下前端由后端托管，改完要 `npm run build` 才生效。开发时用 dev server 免构建：

```bash
cd web
npm install
npm run dev                     # http://localhost:5173
```

此时后端仍需单独跑，并用 `FRONTEND_URL=http://localhost:5173` 启动，
这样 Gmail 授权回调才会跳回 5173 而不是 8000。

## 二、凭据怎么存的

| 凭据 | 存放位置 | 说明 |
|---|---|---|
| 随手记账号密码 | 浏览器本地 | 服务端不存密码，只在内存中换 token |
| 神象云 token | 服务端会话（落盘 sessions.db） | 进程重启后仍可恢复 |
| Gmail OAuth token | 浏览器本地 | 一次授权长期有效；服务端只在授权瞬间中转 |
| Gmail 授权中的 PKCE verifier | 服务端会话（落盘 sessions.db） | 临时，用完即删；见下节 |
| 账户映射 / 记账规则 | SQLite（autosui.db） | 只有配置，没有密码 |

**因为要传密码，正式部署必须上 HTTPS**，否则密码在链路上是明文。用 Nginx 反代 + Let's Encrypt 证书即可。

### 会话落盘（sessions.db）

会话默认落盘到项目根目录的 `sessions.db`（`sessions.db` 已在 `.gitignore` 里）。这是为了解决一个具体问题：**Gmail 授权过程中服务若重启，授权就白做了**。

原因在于 OAuth 是「重定向出去再回来」的流程：点授权时后端把 PKCE 的 `code_verifier` 存在会话里 → 跳到 Google → 用户在 Google 页面登录、同意（可能几十秒到几分钟）→ 带回 `code` 回调。如果这段时间服务重启（比如开着 `RELOAD=1` 改了代码），内存里的会话连同 verifier 一起消失，回调只能报「授权会话已失效」，用户反复重试也没用。

现在会把会话落盘，并且单独存一份可序列化的 `code_verifier`，进程重启后能重建 flow，让这次授权照常完成。

想改回纯内存模式（凭据完全不落盘）：

```bash
AUTOSUI_SESSION_FILE= python run_server.py
```

也可以改会话有效期（默认 8 小时）：`AUTOSUI_SESSION_TTL=3600`。

### Gmail 凭据的生命周期

授权完成后，前端调 `/api/gmail/claim` 把凭据领回存到浏览器本地，服务端随即删除自己的副本。之后每次读邮件，前端把凭据随请求带上；access_token 过期时服务端自动用 refresh_token 续期，并把续期后的凭据回传、前端覆盖保存。

所以只要 refresh_token 有效（通常长期有效，除非用户主动撤销），**退出登录、关闭浏览器、重启服务都不需要重新授权**。

> 注意：退出登录（`clearLocal`）**刻意保留** `autosui.gmailCreds`，只有点「删除授权」才会清。改这块代码时别把这条规则弄丢。

想撤销就在 Gmail 标签页点「删除授权」，会清除本机保存的凭据（不影响 Google 账号侧的授权记录，要彻底撤销需到 Google 账号设置的「第三方应用访问权限」里移除）。

## 三、Gmail 账单功能配置

1. 到 [Google Cloud Console](https://console.cloud.google.com/) 创建项目，启用 **Gmail API**
2. 「凭据」→ 创建 **OAuth 客户端 ID** → 应用类型选 **Web 应用**
3. 已授权的重定向 URI 填：
   ```
   http://localhost:8000/api/gmail/callback
   ```
   （正式部署换成你的域名，并设置 `GOOGLE_REDIRECT_URI` 环境变量）
4. 下载 JSON，放到项目根目录，命名为 `credentials.json`

### ⚠️ 国内网络必须配代理

Google 的 token 端点 `oauth2.googleapis.com` **在境内无法直连**。不配代理时典型症状是：浏览器里授权明明成功了，跳回来却是 `?gmail=error`——因为服务端拿 code 去换 token 时连不上，而且要干等很久才报错。

启动服务时带代理（Clash / V2Ray 默认端口）：

```bash
HTTPS_PROXY=socks5://127.0.0.1:10808 python run_server.py
# 或走 HTTP 代理
HTTPS_PROXY=http://127.0.0.1:10809 python run_server.py
```

验证代理是否可用：

```bash
curl -x socks5://127.0.0.1:10808 https://oauth2.googleapis.com/.well-known/openid-configuration
```

> 实现说明：`requests` / `requests_oauthlib`（授权、换 token）会自动读 `HTTPS_PROXY`；
> 但 `googleapiclient` 底层是 `httplib2`，**不认环境变量**，代码里已显式注入代理（见 `gmail_service.__http`）。
> 若哪天改回 `build(..., credentials=creds)`，会出现「授权成功但读邮件超时」的一半能用一半不能的状态。

可用环境变量：

```bash
HTTPS_PROXY=socks5://127.0.0.1:10808    # 代理,国内必需
GOOGLE_TIMEOUT=15                        # Google 请求超时秒数,默认 15
GOOGLE_CREDENTIALS=/path/to/credentials.json
GOOGLE_REDIRECT_URI=https://your.domain/api/gmail/callback
FRONTEND_URL=https://your.domain
ALLOW_ORIGINS=https://your.domain
PORT=8000
```

查询当前代理是否生效：`GET /api/gmail/status?sid=xxx` 会返回 `proxy` 字段。

> 注意：未通过 Google 验证的 OAuth 应用最多只能加 100 个测试用户，
> 需要在「OAuth 同意屏幕」里把使用者加为测试用户，否则授权会被拦截。

## 四、页面流程

1. **登录**：输入随手记账号密码 → 选择账本（**神象云账本 + 旧随手记账本**） → 进入
   - 两类账本分别取自两个接口，互不重叠，直接拼接：
     | 类型 | 接口 | 操作类 | provider 标签 |
     |---|---|---|---|
     | 神象云账本 | `yun.feidee.net/cab-index-ws/v3/book-group/cloud` | `shenxiang.py` | 神象云 |
     | 旧随手记账本 | `tally.feidee.net/mini_program/v1/books/list` | `sui.py` | 旧版 |
   - 任一接口失败只影响那一类账本，另一类照常可用。
   - **密码登录被风控拦截时（code 4099「客户端参数为空」）**，点登录框下方的「用 access_token 登录」，把浏览器会话里的 token 粘进去即可绕过（详见 [1.1](#11-图形验证码旁路token-登录)）。
2. **导入账单**
   - 上传：先选「账单类型」（农行 / 建行）→ 选文件 → 解析。**不再用文件名判断银行**。
   - Gmail：先授权 → 读取账单邮件 → 勾选 → 加载
3. **对账**：选记账账户后自动比对账本流水
   - 已入账：显示账本里的对应记录
   - 规则可自动：一键按规则记账
   - 待记账：点「记账」选方式、分类、备注，可顺便存为规则
   - 鼠标悬停「账本记录」列可看明细：分类、对方账户、备注、时间、流水 id、成员。转账场景额外展示「转出 → 转入」双方账户。
4. **记账**：按 `日期 + 金额 + 收支方向` 去重，不会重复入账

### 1.1 图形验证码旁路：token 登录

神象云服务端会对密码登录加图形验证码风控，此时登录会失败并报：

```
神象云登录失败: 登录失败: 客户端参数为空（可在下方填入 access_token 绕过）
```

「客户端参数为空」是服务端索取 `vcid`（验证码凭据）的信号，并非真的缺参数。绕过办法是复用浏览器里那颗仍然有效的 token：

1. 浏览器打开并登录 <https://www.feidee.com/cloud/>
2. F12 → Console，执行 `copy(localStorage.Authorization)`
3. 回到 auto-sui 登录页 → 点「密码登录失败？用 access_token 登录」→ 粘贴

后端拿到 token 后直接灌进 `ShenxiangClient`，**不发起密码登录**，因此不会触发验证码。token 只存在于内存会话中，不落库。
5. **自动记账规则**：顶部菜单「自动记账规则」进入独立管理页
   - 列出全部规则的匹配条件、分类、命中次数
   - 编辑（条件编辑器）/ 删除 / 调优先级
   - 新增规则（手动指定条件）

## 五、规则引擎

老版本用 Python `eval` 执行 `transType == 'payout' and ...` 这类表达式，**多用户场景下任何登录用户都能借规则执行任意代码**（读文件、枚举数据库）。新版本改成结构化条件：
- 字段白名单：`opAccName / opAccNo / memo / usage / amount / transType`
- 匹配方式白名单：`eq / contains / startswith / regex / gt / lt`
- 多条条件之间是 AND，按 priority 降序匹配第一条命中
- 前端编辑器由下拉框 + 输入框组成，杜绝手写任意代码
- 历史数据已通过 `expToConditions` 自动迁移到新格式（在 `initDb()` 时自动跑）

后端校验代码在 `server/main.py:validateConditions`，前端字段常量在 `web/src/api.js:api.ruleFields` / `api.ruleMatches`。

## 五、接口一览

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | /api/login | 登录，返回账本列表。可选 `shenxiangToken` 绕过验证码风控 |
| POST | /api/book | 切换账本，返回账户与分类 |
| GET | /api/accounts · /api/categories | 账本账户 / 分类 |
| GET · POST | /api/mapping | 银行卡号 → 账本账户映射 |
| POST | /api/bills/readers | 列出前端支持的账单类型（农行/建行 等） |
| POST | /api/bills/upload | 上传并解析账单（form 字段：`sid`、`bankType`、`file`） |
| POST | /api/reconcile | 对账，返回每条状态 |
| POST | /api/tally | 记账 |
| GET · POST · PUT · DELETE | /api/rules | 自动记账规则（结构化条件） |
| GET | /api/gmail/auth-url | 生成 Gmail 授权地址 |
| POST | /api/gmail/claim | 授权后把凭据领回浏览器（一次性） |
| POST | /api/gmail/mails | 账单邮件列表（body 带凭据） |
| POST | /api/gmail/load | 加载所选邮件里的账单（body 带凭据） |

## 六、测试

```bash
python run_server.py            # 另开终端
python test_api.py              # 登录→选账本→上传→对账 冒烟测试
python test_api.py --tally      # 额外记一笔（会写入当前账本）
python test_rules.py            # 规则 CRUD + 匹配引擎测试
python test_rules_http.py       # 规则 API 入参校验（白名单拦截）
python test_bill_readers.py     # 账单类型选择 + 白名单 + ValueError 文案
python test_matched_detail.py   # 账本流水详情字段扩展 + Beijing tz 修正
python test_provider_routing.py # 多 provider（神象云 vs 旧随手记）登录/切换/路由
python test_client_routing.py   # 两个 client 不互相覆盖
python test_book_list.py        # 两来源账本清单 + token 登录旁路 + 旧账本切换
```

## 七、多体系账本（神象云 + 旧随手记）

### 两类账本的来源与路由

| | 神象云账本 | 旧随手记账本 |
|---|---|---|
| 清单接口 | `yun.feidee.net/cab-index-ws/v3/book-group/cloud` | `tally.feidee.net/mini_program/v1/books/list` |
| 操作实现 | `shenxiang.py` | `sui.py` |
| provider | `shenxiang` | `legacy` |
| client 存储 | `s["client"]` | `s["legacyClient"]` |

⚠️ **旧账本虽然要靠神象云的 token 才能列出来，但不能用神象云 client 操作**。实测
`setBookId(旧账本id) + initTallyInfo` 拉回来的账户 / 分类**全是空列表** —— 神象云 SDK
只认自己的账本。所以它们一律路由 `provider=legacy` 交给 `sui.py`。

`sui.py` 的账本切换走 `systemSet/book.do?opt=switch&switchId=<id>`，是服务端会话状态；
因此切换后必须重跑 `initTallyInfo()`，否则拿回的是上一个账本的分类和账户。原先
`switchId` 写死成单个默认账本，第二个旧账本根本进不去，现已改为参数化。

### 登录时的降级

- 神象云登录失败 → 直接 400，没有账本什么都干不了（可用 access_token 绕过，见 1.1）
- 旧体系登录失败（login.sui.com 不通 / 风控 / 页面结构变化）→ 优雅降级，旧账本仍列出但不可选，不影响神象云账本

切到旧账本后：
- 账户 / 分类：从 sui.py 解析的 HTML 拉来，前端级联 `[id, name, children]` 一致形态
- 记账（payout / income / transfer）：路由到 `sui.py` 的同名方法，参数顺序与神象云一致
- 对账：legacy detail 走 `_normalizeLegacyDetails` 模糊归一化，让 reconcile 引擎拿到 `sdate / itemAmount / tranType / *AcountId`；缺字段兜 0，绝不抛 5xx

后端按 `provider` 路由，前端不感知 —— 选中账本后 `state.bookId` 后端已经自动绑好 client。
