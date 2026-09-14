# -*- coding: utf-8 -*-
"""启动 auto-sui Web 服务。

用法:
    python run_server.py              # 默认 http://127.0.0.1:8000
    PORT=8080 python run_server.py    # 换端口

前端开发模式另开一个终端:
    cd web && npm install && npm run dev     # http://localhost:5173

会话持久化:
    默认把会话落盘到 <项目根>/sessions.db(启动前可用 AUTOSUI_SESSION_FILE 覆盖;
    置为空字符串即退回纯内存模式)。原因: Gmail OAuth 要把用户重定向到 Google
    页面再回调回来,若这期间服务重启(reload / 手动重启),内存里的会话和
    PKCE code_verifier 就没了,回调只能报「授权会话已失效」。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# 在导入 server.main 之前设好,因为 session_store 在模块导入时就会读这个变量
os.environ.setdefault("AUTOSUI_SESSION_FILE", os.path.join(HERE, "sessions.db"))

import uvicorn  # noqa: E402

if __name__ == "__main__":
    # HOST 默认 0.0.0.0(本地/容器友好);生产用 nginx 反代时建议设 127.0.0.1,
    # 只让本机 nginx 访问,对外只暴露 80/443。
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    reload = os.environ.get("RELOAD", "1") == "1"
    print("启动 auto-sui 服务: http://%s:%d" % (host, port))
    print("会话持久化: %s" % (os.environ.get("AUTOSUI_SESSION_FILE") or "(内存模式)"))
    uvicorn.run("server.main:app", host=host, port=port, reload=reload)
