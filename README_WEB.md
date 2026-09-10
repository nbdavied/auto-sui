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
| Gmail OAuth token | 服务端内存 | 会话级，不写 token.pickle |
| 账户映射 / 记账规则 | SQLite（autosui.db） | 只有配置，没有密码 |

**因为要传密码，正式部署必须上 HTTPS**，否则密码在链路上是明文。用 Nginx 反代 + Let's Encrypt 证书即可。

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

1. **登录**：输入随手记账号密码 → 选择账本 → 进入
2. **导入账单**
   - 上传：选农行 `abc*.xlsx` / 建行 `hqmx*.xlsx`
   - Gmail：先授权 → 读取账单邮件 → 勾选 → 加载
3. **对账**：选记账账户后自动比对账本流水
   - 已入账：显示账本里的对应记录
   - 规则可自动：一键按规则记账
   - 待记账：点「记账」选方式、分类、备注，可顺便存为规则
4. **记账**：按 `日期 + 金额 + 收支方向` 去重，不会重复入账

## 五、接口一览

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | /api/login | 登录神象云，返回账本列表 |
| POST | /api/book | 切换账本，返回账户与分类 |
| GET | /api/accounts · /api/categories | 账本账户 / 分类 |
| GET · POST | /api/mapping | 银行卡号 → 账本账户映射 |
| POST | /api/bills/upload | 上传并解析账单 |
| POST | /api/reconcile | 对账，返回每条状态 |
| POST | /api/tally | 记账 |
| GET · POST · DELETE | /api/rules | 自动记账规则 |
| GET | /api/gmail/auth-url · /api/gmail/mails | Gmail 授权与邮件列表 |
| POST | /api/gmail/load | 加载所选邮件里的账单 |

## 六、测试

```bash
python run_server.py            # 另开终端
python test_api.py              # 登录→选账本→上传→对账 冒烟测试
python test_api.py --tally      # 额外记一笔（会写入当前账本）
```
