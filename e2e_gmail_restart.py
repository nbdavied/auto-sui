# -*- coding: utf-8 -*-
"""真实「重启恢复」验证: 起一个真服务 -> 造会话+flow -> 杀进程 -> 重启 -> 回调。

这是对用户症状最直接的复刻。为避免依赖随手记登录,会话直接用 session_store
在独立进程里落盘,再让新进程读回来。
"""
import os
import subprocess
import sys
import tempfile
import time
import json
import importlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

PY = r"C:/Users/nbdav/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
DB = os.path.join(tempfile.gettempdir(), "autosui_restart_test.db")
if os.path.exists(DB):
    os.remove(DB)

print("=== 阶段 1: 进程 A 创建会话 + 写入 PKCE verifier + 落盘 ===")
env = dict(os.environ)
env["AUTOSUI_SESSION_FILE"] = DB
code = (
    "import sys; sys.path.insert(0, r'%s');"
    "from server import session_store as ss;"
    "sid = ss.create();"
    "ss.setField(sid, 'username', 'restart@e.com');"
    "ss.setField(sid, 'gmailFlowState', {'codeVerifier': 'VERIFIER-FROM-PROCESS-A', "
    "'redirectUri': 'http://localhost:8000/api/gmail/callback'});"
    "print(sid)" % HERE
)
out = subprocess.run([PY, "-c", code], capture_output=True, text=True, env=env)
sid = out.stdout.strip().splitlines()[-1]
print("进程 A 创建 sid:", sid)
if not sid:
    print("stdout:", out.stdout, "\nstderr:", out.stderr)
    sys.exit(1)

print("\n=== 阶段 2: 进程 A 已退出(模拟服务重启), 进程 B 读回 ===")
code2 = (
    "import sys, json; sys.path.insert(0, r'%s');"
    "from server import session_store as ss;"
    "s = ss.get(r'%s');"
    "print(json.dumps({'found': s is not None,"
    "'username': (s or {}).get('username'),"
    "'flowState': (s or {}).get('gmailFlowState')}, ensure_ascii=False))" % (HERE, sid)
)
out2 = subprocess.run([PY, "-c", code2], capture_output=True, text=True, env=env)
print("进程 B 结果:", out2.stdout.strip() or out2.stderr[-400:])
data = json.loads(out2.stdout.strip().splitlines()[-1])

ok = True
if not data["found"]:
    print("FAIL 新进程没读到会话")
    ok = False
else:
    if data["username"] != "restart@e.com":
        print("FAIL username 未恢复:", data["username"]); ok = False
    if (data["flowState"] or {}).get("codeVerifier") != "VERIFIER-FROM-PROCESS-A":
        print("FAIL PKCE verifier 未恢复:", data["flowState"]); ok = False

print("\n=== 阶段 3: 新进程用恢复的 verifier 重建 flow ===")
code3 = (
    "import sys; sys.path.insert(0, r'%s');"
    "from server import session_store as ss;"
    "from server import gmail_service as gs;"
    "s = ss.get(r'%s');"
    "f = gs.flowFromState(s.get('gmailFlowState'));"
    "print('REBUILT' if f is not None else 'FAILED');"
    "print('VERIFIER_OK' if (f is not None and f.code_verifier == 'VERIFIER-FROM-PROCESS-A') else 'VERIFIER_MISMATCH')" % (HERE, sid)
)
env2 = dict(env)
env2["HTTPS_PROXY"] = "socks5://127.0.0.1:10808"
out3 = subprocess.run([PY, "-c", code3], capture_output=True, text=True, env=env2)
print(out3.stdout.strip() or out3.stderr[-400:])
if "REBUILT" not in out3.stdout:
    print("FAIL 未能重建 flow"); ok = False
if "VERIFIER_OK" not in out3.stdout:
    print("FAIL verifier 不一致"); ok = False

try:
    os.remove(DB)
except OSError:
    pass

print("\n结果:", "重启恢复验证通过" if ok else "存在失败项")
sys.exit(0 if ok else 1)
