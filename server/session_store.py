# -*- coding: utf-8 -*-
"""会话存储。

会话里保存的是「本次登录换来的神象云 token」和「Gmail OAuth 凭据」。

持久化策略(2026-09 调整):
  - 默认仍是**内存会话**,进程重启即失效 —— 凭据不落盘是安全上的默认选择。
  - 但 Gmail OAuth 是「重定向出去的」流程: 用户在 Google 页面停留期间,
    如果服务进程重启(reload、手动重启、崩溃),内存里的会话连同
    gmailFlow(PKCE code_verifier)一起消失,回调回来只会看到
    ?gmail=expired —— 这正是「授权用不了」的主要成因。
  - 所以当环境变量 AUTOSUI_TTL_SECONDS/AUTOSUI_SESSION_FILE 允许时,
    会话落盘到 SQLite,重启后仍能找回 flow 与凭据。

浏览器侧保存的是随手记账号密码 + session id。
"""
import json
import os
import sqlite3
import threading
import time
import uuid

SESSION_TTL = int(os.environ.get("AUTOSUI_SESSION_TTL", str(8 * 3600)))  # 8 小时
# 置空字符串即退回纯内存模式(默认)。设成文件路径则开启持久化。
SESSION_FILE = os.environ.get("AUTOSUI_SESSION_FILE", "").strip()

_lock = threading.Lock()
_sessions = {}

# 不需要落盘的字段(含大对象/不可序列化对象): flow 是 OAuth 内部对象,
# 每个会话只有一两份,且主要在「授权 -> 回调」这段极短时间内存活。
# 但正因为它是回调必需的,所以必须一起落盘 —— 见 _serialize。
_NO_PERSIST = {"gmailFlow"}


def _connect():
    conn = sqlite3.connect(SESSION_FILE, timeout=10)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            sid       TEXT PRIMARY KEY,
            payload   TEXT NOT NULL,
            createdAt REAL NOT NULL
        )
    """)
    return conn


def _persistable(s):
    """会话里能落盘的键值对。"""
    out = {}
    for k, v in s.items():
        if k in _NO_PERSIST:
            continue
        if isinstance(v, (str, int, float, bool, type(None), list, dict)):
            out[k] = v
    return out


def _save(s):
    if not SESSION_FILE:
        return
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sessions (sid, payload, createdAt) VALUES (?, ?, ?)",
                (s["sid"], json.dumps(_persistable(s), ensure_ascii=False),
                 s["createdAt"]))
            conn.commit()
    except Exception as e:
        print("[session] 落盘失败(忽略): %s" % e)


def _loadAll():
    """进程启动时把未过期的会话捞回来。"""
    if not SESSION_FILE:
        return
    if not os.path.exists(SESSION_FILE):
        return
    try:
        with _connect() as conn:
            rows = conn.execute("SELECT sid, payload, createdAt FROM sessions").fetchall()
    except Exception as e:
        print("[session] 读取失败(忽略): %s" % e)
        return
    now = time.time()
    loaded = 0
    for sid, payload, createdAt in rows:
        if now - createdAt > SESSION_TTL:
            continue
        try:
            data = json.loads(payload)
        except Exception:
            continue
        data["sid"] = sid
        data["createdAt"] = createdAt
        _sessions[sid] = data
        loaded += 1
    if loaded:
        print("[session] 从 %s 恢复 %d 个会话" % (SESSION_FILE, loaded))


def create():
    sid = uuid.uuid4().hex
    with _lock:
        _sessions[sid] = {"sid": sid, "createdAt": time.time()}
    return sid


def get(sid):
    if not sid:
        return None
    with _lock:
        s = _sessions.get(sid)
    if not s:
        return None
    if time.time() - s["createdAt"] > SESSION_TTL:
        destroy(sid)
        return None
    return s


def setField(sid, key, value):
    s = get(sid)
    if s is None:
        return False
    s[key] = value
    _save(s)
    return True


def destroy(sid):
    with _lock:
        _sessions.pop(sid, None)
    if SESSION_FILE:
        try:
            with _connect() as conn:
                conn.execute("DELETE FROM sessions WHERE sid = ?", (sid,))
                conn.commit()
        except Exception:
            pass


def cleanExpired():
    now = time.time()
    with _lock:
        for sid in [k for k, v in _sessions.items() if now - v["createdAt"] > SESSION_TTL]:
            _sessions.pop(sid, None)
    if SESSION_FILE:
        try:
            with _connect() as conn:
                conn.execute("DELETE FROM sessions WHERE createdAt < ?",
                             (now - SESSION_TTL,))
                conn.commit()
        except Exception:
            pass


_loadAll()
