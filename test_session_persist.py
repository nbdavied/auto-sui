# -*- coding: utf-8 -*-
"""验证: 会话落盘后,进程重启(gmailFlow 丢失)不再让 Gmail 授权流程崩掉。

这条链路是「授权失败」的主要成因:
  点授权 -> 后端把 flow(PKCE verifier)存进会话 -> 跳 Google
  -> 用户登录/同意(耗时几十秒到几分钟) -> 回调带 code+state 回来
如果这段时间服务重启,原实现内存会话全丢,回调只能 ?gmail=expired。

运行: pytest test_session_persist.py -q
"""
import os
import sys
import time
import tempfile
import importlib

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """每个用例一个干净的落盘库,避免互相污染。"""
    monkeypatch.setenv("AUTOSUI_SESSION_FILE", str(tmp_path / "sessions.db"))
    from server import session_store
    return importlib.reload(session_store)


def testCreateAndRead(store):
    sid = store.create()
    store.setField(sid, "username", "u@e.com")
    s = store.get(sid)
    assert s is not None
    assert s["username"] == "u@e.com"


def testRestartRestoresSession(store):
    """核心: 清空内存 + 重新导入模块(等价于进程重启),会话应恢复。"""
    sid = store.create()
    store.setField(sid, "username", "u@e.com")
    store.setField(sid, "userId", 7)
    store.setField(sid, "gmailFlowState", {"codeVerifier": "v-abc"})

    store._sessions.clear()
    reloaded = importlib.reload(store)

    s = reloaded.get(sid)
    assert s is not None, "重启后会话应能从磁盘恢复"
    assert s["username"] == "u@e.com"
    assert s["userId"] == 7
    assert s["gmailFlowState"] == {"codeVerifier": "v-abc"}
    assert s["createdAt"] > 0, "createdAt 必须保留,否则每次重启都在续期"


def testExpiredSessionNotRestored(store):
    sid = store.create()
    store.setField(sid, "username", "stale@e.com")
    with store._lock:
        store._sessions[sid]["createdAt"] = time.time() - 9 * 3600  # 超过 8 小时
    store._save(store.get(sid))

    reloaded = importlib.reload(store)
    assert reloaded.get(sid) is None, "过期会话不应被恢复"


def testDestroyRemovesFromDisk(store):
    sid = store.create()
    store.setField(sid, "username", "gone@e.com")
    store.destroy(sid)

    reloaded = importlib.reload(store)
    assert reloaded.get(sid) is None, "destroy 后重启也不该看到"


def testUnserializableFieldIgnored(store):
    """gmailFlow 是无法 pickle/JSON 的对象,落盘时要安全跳过而不是抛错。"""
    sid = store.create()
    store.setField(sid, "username", "obj@e.com")
    with store._lock:
        store._sessions[sid]["gmailFlow"] = object()

    store._save(store.get(sid))  # 不应抛错

    reloaded = importlib.reload(store)
    s = reloaded.get(sid)
    assert s is not None
    assert s["username"] == "obj@e.com"
    assert "gmailFlow" not in s, "不可序列化对象不该出现在恢复结果里"


def testMemoryModeWhenNoFile(monkeypatch):
    """AUTOSUI_SESSION_FILE 为空时退回纯内存模式(默认行为)。"""
    monkeypatch.setenv("AUTOSUI_SESSION_FILE", "")
    from server import session_store
    reloaded = importlib.reload(session_store)
    assert reloaded.SESSION_FILE == ""

    sid = reloaded.create()
    reloaded.setField(sid, "username", "mem@e.com")
    reloaded._sessions.clear()
    again = importlib.reload(reloaded)
    assert again.get(sid) is None, "内存模式下重启即失效"
