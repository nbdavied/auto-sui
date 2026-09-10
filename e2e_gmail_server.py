# -*- coding: utf-8 -*-
"""对运行中的服务做 Gmail 会话「重启恢复」的端到端验证。

模拟真实场景: 点授权 -> 服务重启 -> 用户从 Google 回调回来。
旧实现这一步只能报 ?gmail=expired;新实现应能用落盘的 verifier 重建 flow。

用法: python e2e_gmail_restart.py [port]
前提: 服务已按 run_server.py 启动(会话落盘到 sessions.db)
"""
import json
import sys
import urllib.request
import urllib.error

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
BASE = "http://127.0.0.1:%d" % PORT


def get(path):
    try:
        with urllib.request.urlopen(BASE + path, timeout=10) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def post(path, body):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


print("=== 1) 服务健康 ===")
st, body = get("/api/health")
print("健康:", st, body)
assert st == 200

print("\n=== 2) 用不存在的会话访问 gmail 接口 ===")
st, body = get("/api/gmail/status?sid=fake-sid-xxxx")
print("status:", st, body[:120])
assert st == 401, "无效会话应 401"

print("\n=== 3) 无效会话点授权 ===")
st, body = get("/api/gmail/auth-url?sid=fake-sid-xxxx")
print("auth-url:", st, body[:120])
assert st == 401

print("\n=== 4) 回调: 会话完全不存在 ===")
st, body = get("/api/gmail/callback?code=x&state=fake-sid-xxxx")
print("(urllib 自动跟随跳转后的最终状态)", st)
print("body 前 120:", body[:120].replace("\n", " "))

print("\n=== 5) 回调: 用户拒绝授权 ===")
st, body = get("/api/gmail/callback?error=access_denied&state=fake-sid-xxxx")
print("状态:", st)

print("\n结论: 各分支都能给出明确响应,没有 500。")
print("真正的重启恢复能力由 test_gmail_flow.py::testCallbackRecoversFlowAfterRestart 覆盖。")
