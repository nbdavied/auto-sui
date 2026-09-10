# -*- coding: utf-8 -*-
"""启动 auto-sui Web 服务。

用法:
    python run_server.py              # 默认 http://127.0.0.1:8000
    PORT=8080 python run_server.py    # 换端口

前端开发模式另开一个终端:
    cd web && npm install && npm run dev     # http://localhost:5173
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn  # noqa: E402

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    reload = os.environ.get("RELOAD", "1") == "1"
    print("启动 auto-sui 服务: http://127.0.0.1:%d" % port)
    uvicorn.run("server.main:app", host="0.0.0.0", port=port, reload=reload)
