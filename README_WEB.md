# auto-sui Web 版使用说明

浏览器里完成「登录 → 导入账单 → 对账 → 记账」，支持多用户，各自用自己的随手记账号和 Gmail。

## 一、启动

### 1. 后端

```bash
pip install -r requirements.txt
python run_server.py            # http://127.0.0.1:8000
```

### 2. 前端

开发模式（改代码热更新）：

```bash
cd web
npm install
npm run dev                     # http://localhost:5173
```

生产模式（构建后由后端直接托管，只需跑后端）：

```bash
cd web && npm run build         # 产出 web/dist
python run_server.py            # 直接访问 http://127.0.0.1:8000
```

## 二、凭据怎么存的

| 凭据 | 存放位置 | 说明 |
|---|---|---|
| 随手记账号密码 | 浏览器本地 | 服务端不存密码，只在内存中换 token |
| 神象云 token | 服务端内存 | 会话级，进程重启即失效 |
| Gmail OAuth token | 浏览器本地 | 一次授权长期有效；服务端只在授权瞬间中转 |
| 账户映射 / 记账规则 | SQLite（autosui.db） | 只有配置，没有密码 |

**因为要传密码，正式部署必须上 HTTPS**，否则密码在链路上是明文。用 Nginx 反代 + Let's Encrypt 证书即可。

### Gmail 凭据的生命周期

授权完成后，前端调 `/api/gmail/claim` 把凭据领回存到浏览器本地，服务端随即删除自己的副本。之后每次读邮件，前端把凭据随请求带上；access_token 过期时服务端自动用 refresh_token 续期，并把续期后的凭据回传、前端覆盖保存。

所以只要 refresh_token 有效（通常长期有效，除非用户主动撤销），**退出登录、关闭浏览器、重启服务都不需要重新授权**。

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

1. **登录**：输入随手记账号密码 → 选择账本（**支持神象云账本 + 旧随手记账本**） → 进入
2. **导入账单**
   - 上传：先选「账单类型」（农行 / 建行）→ 选文件 → 解析。**不再用文件名判断银行**。
   - Gmail：先授权 → 读取账单邮件 → 勾选 → 加载
3. **对账**：选记账账户后自动比对账本流水
   - 已入账：显示账本里的对应记录
   - 规则可自动：一键按规则记账
   - 待记账：点「记账」选方式、分类、备注，可顺便存为规则
   - 鼠标悬停「账本记录」列可看明细：分类、对方账户、备注、时间、流水 id、成员。转账场景额外展示「转出 → 转入」双方账户。
4. **记账**：按 `日期 + 金额 + 收支方向` 去重，不会重复入账
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
| POST | /api/login | 登录神象云，返回账本列表 |
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
```

## 七、多体系账本（神象云 + 旧随手记）

同一个随手记账号可能既建了神象云账本、又保留旧版本（sui.com）的账本。本服务登录时同时尝试登录两边：
- 神象云登录失败 → 直接 400，没有账本什么都干不了
- 旧体系登录失败（login.sui.com 不通 / 验证码风控）→ 优雅降级，旧账本选项不出现，但不影响主流程

切到旧账本后：
- 账户 / 分类：从 sui.py 解析的 HTML 拉来，前端级联 `[id, name, children]` 一致形态
- 记账（payout / income / transfer）：路由到 `sui.py` 的同名方法，参数顺序与神象云一致
- 对账：legacy detail 走 `_normalizeLegacyDetails` 模糊归一化，让 reconcile 引擎拿到 `sdate / itemAmount / tranType / *AcountId`；缺字段兜 0，绝不抛 5xx

后端按 `provider` 路由，前端不感知 —— 选中账本后 `state.bookId` 后端已经自动绑好 client。
