# auto-sui 部署指南（Ubuntu 22.04 · 后端与 Nginx 分离）

把 auto-sui 拆成两层部署：
- **后端 VM（本机）**：只跑一个 uvicorn 进程（同时托管前端静态文件），监听 `0.0.0.0:8000`，**不装 Nginx、不申请证书、不碰防火墙**。
- **另一台 Nginx 服务器（带域名 + TLS）**：反代到后端 VM 的 `8000` 端口，做 HTTPS 终止。

本指南配套 `deploy/` 里的脚本与模板。概念与环境变量（代理、会话落盘、Gmail 原理）在根目录 `README_WEB.md` 讲得更细。

---

## 0. 架构

```
浏览器 ──HTTPS──> Nginx 服务器(:443, 有域名证书)
                     │  反代 proxy_pass http://后端VM:8000
                     ▼
               uvicorn 后端 VM(:8000, 仅本机)
                     ├─ FastAPI 提供 /api/*
                     └─ 直接托管前端静态文件 web/dist (单进程)
```

- **单进程**：uvicorn 既跑 API 又托管前端（前端 `baseURL` 是相对路径 `/api`，同源、无 CORS）。
- 后端 VM 只暴露 HTTP（`0.0.0.0:8000`），**不要对公网开放**；只放行业务 Nginx 服务器的 IP（在后端 VM 的防火墙/安全组上做限制）。
- **Gmail**：后端服务端用 `HTTPS_PROXY` 把 Google 请求走代理（境内才能连上）。

---

## 1. 前置条件

| 项目 | 说明 |
|---|---|
| 后端 VM | Ubuntu 22.04.3，能用 **root** 登录 |
| Python | 自带 3.10.12，当前可用；但 `google.api_core` 将于 **2026-10-04** 停止支持 3.10（见第 8 节升级） |
| 另一台 Nginx 服务器 | 已绑定域名 + TLS 证书（Let's Encrypt 或自有），能访问后端 VM 的 8000 端口 |
| Gmail | 一个能从后端 VM 连上的代理地址（Clash/V2Ray 的 SOCKS5 或 HTTP 端口） |

---

## 2. 后端 VM：一键部署

`deploy/` 随仓库一起（未被 gitignore），所以 `git clone` 后它就在服务器上。

```bash
# 在后端 VM 上(用 root 或 sudo)
git clone git@github.com:nbdavied/auto-sui.git /opt/auto-sui
cd /opt/auto-sui

# 跑一键脚本(会交互询问域名, 不用 Gmail 可直接回车)
sudo bash deploy/install.sh
```

脚本依次做了：装系统依赖（不含 nginx/certbot）→ 装 Node 20 并构建前端 → 建 venv 装 Python 依赖 → 注册 systemd（开机自启 + 崩溃重启）→ 写 `/etc/auto-sui/env`。
跑完会打印本机服务地址和「下一步在另一台 Nginx 上怎么做」。

> 想免交互预设：`DOMAIN=autosui.example.com GMAIL_PROXY=socks5://127.0.0.1:10808 sudo -E bash deploy/install.sh`

---

## 3. 另一台 Nginx：反代配置

把 `deploy/auto-sui.nginx.conf` 放到那台带证书的 Nginx 上，**替换两个占位符**：
- `__DOMAIN__` → 你的域名
- `__BACKEND_ADDR__` → `http://后端VM的IP:8000`（注意是 http，TLS 已在 Nginx 这层终止）

然后 `nginx -t && systemctl reload nginx`。证书用该服务器上的 `certbot certonly --webroot ...` 正常签发即可（与本项目无关）。

> 反向代理要带上 `X-Forwarded-Proto $scheme` 等头，否则后端看到的协议会是 http，Gmail 回调拼出的地址可能不对。

---

## 4. 手动分步（后端 VM，学习 / 排错用）

```bash
# 系统依赖(不含 nginx/certbot)
apt update
apt install -y git curl python3-venv python3-pip software-properties-common

# Node 20(构建前端, Vite 需 18+)
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs

# 拉代码
git clone git@github.com:nbdavied/auto-sui.git /opt/auto-sui
cd /opt/auto-sui

# 后端依赖
python3 -m venv venv && venv/bin/pip install -r requirements.txt

# 前端构建(产物在 web/dist, 由本机 uvicorn 托管)
cd web && npm install && npm run build && cd ..

# Gmail: 把 credentials.json 放到项目根目录
cp ~/credentials.json /opt/auto-sui/credentials.json

# 运行用户(非 root)
useradd --system --home-dir /var/lib/autosui --create-home --shell /usr/sbin/nologin autosui
chown -R autosui:autosui /opt/auto-sui
```

参考 `deploy/auto-sui.service`（占位符 `__SERVICE_USER__` / `__INSTALL_DIR__`）生成
`/etc/systemd/system/auto-sui.service`，再 `systemctl daemon-reload && systemctl enable --now auto-sui`。
环境变量文件 `/etc/auto-sui/env` 模板见 `deploy/env.template`。

---

## 5. 环境变量（全表）

| 变量 | 作用 | 默认值 / 建议 |
|---|---|---|
| `HOST` | 监听地址 | `0.0.0.0`（供对端 nginx 反代；切勿只听 127.0.0.1 否则跨机连不上） |
| `PORT` | 监听端口 | `8000` |
| `RELOAD` | 改代码自动重启 | `0`（生产必须 0，否则会打断 Gmail 授权） |
| `AUTOSUI_SESSION_FILE` | 会话落盘路径 | `<项目>/sessions.db`；置空 = 纯内存 |
| `AUTOSUI_SESSION_TTL` | 会话有效期(秒) | `28800`（8 小时） |
| `FRONTEND_URL` | OAuth 回调跳回的前端地址 | `https://域名`（否则跳回本机地址） |
| `GOOGLE_REDIRECT_URI` | Google 回调地址 | `https://域名/api/gmail/callback` |
| `HTTPS_PROXY` / `HTTP_PROXY` | Gmail 走代理 | 境内必需，如 `socks5://127.0.0.1:10808` |
| `GOOGLE_TIMEOUT` | Google 请求超时(秒) | `15` |
| `GOOGLE_CREDENTIALS` | credentials.json 路径 | 默认取项目根 `credentials.json` |
| `ALLOW_ORIGINS` | CORS 白名单 | `*`；同源时无需改 |
| `AUTO_SUI_DB` | 账户映射库路径 | `<项目>/autosui.db` |

> 代理细节：代码里 `requests` 和 `httplib2` 都会读 `HTTPS_PROXY`（见 `server/gmail_service.py`）。
> 因为请求库会自动套用这个代理，**建议用 Clash 的「规则模式」**——国内流量（随手记/神象云）直连，国外（Google）走代理。

---

## 6. Gmail 专项（境内后端 VM 必读）

1. **credentials.json**：[Google Cloud Console](https://console.cloud.google.com/) 建项目 → 启用 Gmail API →
   创建 **OAuth 客户端 ID**（应用类型 **Web 应用**）→ 下载 JSON，放到后端 VM 项目根目录 `credentials.json`（已 gitignore）。
2. **重定向 URI**：在 Google Cloud「已授权的重定向 URI」加 `https://你的域名/api/gmail/callback`
   （必须 HTTPS，且与 `GOOGLE_REDIRECT_URI` 完全一致；域名是 Nginx 那台的）。
3. **同意屏幕**：未通过验证的应用最多加 100 个测试用户，记得把要用的人加进「测试用户」。
4. **代理**：在 `/etc/auto-sui/env` 设 `HTTPS_PROXY`，然后 `systemctl restart auto-sui`。
5. **验证**：网页登录 → Gmail 授权 → 跳 Google → 跳回 `?gmail=ok` 即成功。

排错：
- 跳回 `?gmail=error` → 代理不通，或重定向 URI 没登记 / 与 `GOOGLE_REDIRECT_URI` 不一致。
- 跳回 `?gmail=expired` → 授权期间服务重启且会话丢了（已用 `sessions.db` 缓解，但**授权时别 restart**）。
- 诊断：前端调 `/api/gmail/status?sid=xxx` 返回 `proxy` 字段，确认代理生效。

---

## 7. 日常运维

```bash
systemctl status auto-sui          # 状态
journalctl -u auto-sui -f          # 实时日志
systemctl restart auto-sui         # 重启(改了 /etc/auto-sui/env 后必须)
systemctl stop auto-sui            # 停止
```

**更新代码**（拉新版本 + 重建前端 + 重启）：

```bash
cd /opt/auto-sui
git pull
cd web && npm install && npm run build && cd ..
chown -R autosui:autosui /opt/auto-sui
systemctl restart auto-sui
```

**备份**（含账户映射与会话，敏感，妥善保存）：

```bash
cp /opt/auto-sui/autosui.db /opt/auto-sui/sessions.db ~/auto-sui-backup-$(date +%F)/
```

---

## 8. 关于「升级软件版本」

- **Python**：Ubuntu 22.04 自带 **3.10.12**，当前可正常运行；但 `google.api_core`
  已声明将于 **2026-10-04** 停止支持 Python 3.10（import 时打印 `FutureWarning`）。
  在那之前建议升级到 **3.11 或 3.12**，否则 2026-10-04 后拉到新版的 `google-api-core`
  可能装不上或运行时报错。

  **升级做法（不动系统 Python，只重建 venv；`auto-sui.service` 无需改动，因为
  `ExecStart` 指向 `venv/bin/python`，venv 路径保持 `/opt/auto-sui/venv` 不变）：**
  ```bash
  # 一键（停服→备份→装 3.12→重建 venv→重装依赖→起服）:
  sudo bash deploy/upgrade_python.sh
  # 或指定 3.11:
  PYVER=3.11 sudo -E bash deploy/upgrade_python.sh
  ```
  手动步骤（与脚本等价）：
  ```bash
  systemctl stop auto-sui
  add-apt-repository ppa:deadsnakes/ppa
  apt install -y python3.12-venv python3.12-dev
  mv /opt/auto-sui/venv /opt/auto-sui/venv.old
  /usr/bin/python3.12 -m venv /opt/auto-sui/venv
  /opt/auto-sui/venv/bin/pip install -r /opt/auto-sui/requirements.txt
  systemctl restart auto-sui
  ```
  > 数据文件（`autosui.db`/`sessions.db`/`conf.json`）在项目目录，与 venv 无关，不受影响。
- **依赖版本**：`requirements.txt` 未锁版本，`pip` 取兼容新版。想锁定可 `venv/bin/pip freeze > requirements.lock`。
- **Node**：脚本装 20.x，足够 Vite 5，无需额外升级。

---

## 9. 安全建议

- **TLS 在 Nginx 那台做**：用户密码、随手记/神象云 token 走 HTTPS 到 Nginx，再到后端 VM 是内网 HTTP，确保 Nginx→后端这一段也在可信网络内。
- **后端 VM 不对公网开放 8000**：在后端 VM 防火墙/安全组只放行【Nginx 服务器 IP】到 8000。
- **非 root 运行**：后端服务以 `autosui` 系统用户运行。
- **敏感文件**：`credentials.json`（OAuth 客户端密钥）、`autosui.db`、`sessions.db` 别公开，备份时加密。

---

## 10. 常见问题

| 现象 | 原因 / 处理 |
|---|---|
| 用户访问域名 502 | Nginx 连不上后端 VM 的 8000：检查后端 `systemctl status`、Nginx→后端网络、后端防火墙是否只放行了 Nginx IP |
| 前端白屏 / 404 | `web/dist` 没构建。`cd web && npm run build` 后重启 |
| Gmail 跳 `?gmail=error` | 代理不通 或 重定向 URI 未在 Google 登记 |
| Gmail 跳 `?gmail=expired` | 授权期间服务重启；确认 `AUTOSUI_SESSION_FILE` 已设且授权时没 restart |
| 改了环境变量不生效 | 改完必须 `systemctl restart auto-sui` |
