# -*- coding: utf-8 -*-
"""内存会话。

会话里保存的是「本次登录换来的神象云 token」和「Gmail OAuth 凭据」,
只活在进程内存里: 进程重启即失效,不会写入任何持久化存储。
浏览器侧保存的是随手记账号密码 + session id。
"""
import time
import uuid
import threading

SESSION_TTL = 8 * 3600  # 8 小时

_lock = threading.Lock()
_sessions = {}


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
    return True


def destroy(sid):
    with _lock:
        _sessions.pop(sid, None)


def cleanExpired():
    now = time.time()
    with _lock:
        for sid in [k for k, v in _sessions.items() if now - v["createdAt"] > SESSION_TTL]:
            _sessions.pop(sid, None)
