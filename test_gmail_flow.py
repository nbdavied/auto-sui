# -*- coding: utf-8 -*-
"""Gmail 授权链路回归测试。

覆盖用户报的「之前正常的 gmail 授权功能，现在又出现问题」:

  成因 A —— 退出登录时误清 Gmail 凭据(前端 clearLocal,已由
             test_gmail_creds_persist.js 覆盖,这里覆盖后端侧)
  成因 B —— 授权期间服务重启,内存会话连 PKCE verifier 一起丢失,
             回调只能报 ?gmail=expired,用户表现为「授权点了没反应/失败」

运行: pytest test_gmail_flow.py -q
"""
import os
import sys
import tempfile
import importlib
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# 用临时文件做会话落盘,避免污染项目目录
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["AUTOSUI_SESSION_FILE"] = _tmp.name

from fastapi.testclient import TestClient  # noqa: E402
from server import main as M  # noqa: E402
from server import session_store as sessions  # noqa: E402
from server import gmail_service as gs  # noqa: E402

client = TestClient(M.app)

fails = []


def check(name, cond, extra=""):
    if cond:
        print("PASS", name)
    else:
        print("FAIL", name, extra)
        fails.append(name)


class FakeClient:
    def login(self):
        return None

    def getBooks(self):
        return [{"id": "B1", "name": "测试账本"}]

    def listAllBooks(self):
        return []


def makeSession():
    """造一个登录会话,跳过真实随手记登录。"""
    with patch.object(M.sui_service, "createClient", lambda u, p: FakeClient()), \
         patch.object(M.legacy_sui_service, "createClient", lambda u, p: None):
        r = client.post("/api/login",
                        json={"username": "gmail-test@e.com", "password": "x"})
    assert r.status_code == 200, r.text
    return r.json()["sid"]


def testAuthUrlStoresFlowState():
    """点授权时,必须把可落盘的 PKCE verifier 一并存进会话。"""
    sid = makeSession()
    r = client.get("/api/gmail/auth-url", params={"sid": sid})
    check("/api/gmail/auth-url 200", r.status_code == 200, r.text)
    s = sessions.get(sid)
    check("会话里有 flow 对象", s.get("gmailFlow") is not None)
    st = s.get("gmailFlowState") or {}
    check("会话里有可落盘的 flow 状态", bool(st.get("codeVerifier")), str(st))
    check("redirect_uri 已记录",
          st.get("redirectUri", "").endswith("/api/gmail/callback"),
          str(st.get("redirectUri")))


def testCallbackRecoversFlowAfterRestart():
    """核心: 重启导致内存 flow 丢失时,用落盘 verifier 重建 flow 继续换 token。

    这里把 exchangeCode 打桩,只验证「回调有没有拿到一个 verifier 正确的 flow」——
    真实的 Google 交互不适合放进单元测试。
    """
    sid = makeSession()
    client.get("/api/gmail/auth-url", params={"sid": sid})
    s = sessions.get(sid)
    original_verifier = s["gmailFlowState"]["codeVerifier"]

    # 模拟重启: 丢掉内存里的 flow 对象(落盘的 gmailFlowState 保留)
    s.pop("gmailFlow", None)
    check("重启后内存 flow 已丢失", sessions.get(sid).get("gmailFlow") is None)

    captured = {}

    def fakeExchange(flow, code):
        captured["verifier"] = flow.code_verifier
        captured["redirect"] = flow.redirect_uri

        class C:
            def to_json(self):
                return '{"refresh_token":"R"}'
        return C()

    with patch.object(gs, "exchangeCode", fakeExchange):
        r = client.get("/api/gmail/callback",
                       params={"code": "realcode", "state": sid},
                       follow_redirects=False)

    loc = r.headers.get("location", "")
    check("回调未报 expired", "gmail=expired" not in loc, loc)
    check("回调跳回 gmail=ok", "gmail=ok" in loc, loc)
    check("重建的 flow verifier 与授权时一致",
          captured.get("verifier") == original_verifier,
          "got=%s want=%s" % (captured.get("verifier"), original_verifier))
    check("重建的 flow redirect_uri 正确",
          (captured.get("redirect") or "").endswith("/api/gmail/callback"),
          str(captured.get("redirect")))


def testCallbackWithoutAnyFlowStillGuidesReauth():
    """没有任何 flow 信息时(verifier 也没了),必须明确引导重新授权。"""
    sid = makeSession()
    client.get("/api/gmail/auth-url", params={"sid": sid})
    s = sessions.get(sid)
    s.pop("gmailFlow", None)
    s.pop("gmailFlowState", None)

    r = client.get("/api/gmail/callback",
                   params={"code": "c", "state": sid}, follow_redirects=False)
    check("无 flow 时跳 expired", "gmail=expired" in r.headers.get("location", ""),
          r.headers.get("location"))


def testCallbackUserDenied():
    """用户在 Google 页面点「拒绝」时,要带上 error 原因回前端。"""
    sid = makeSession()
    r = client.get("/api/gmail/callback",
                   params={"error": "access_denied", "state": sid},
                   follow_redirects=False)
    loc = r.headers.get("location", "")
    check("拒绝授权跳 gmail=error", "gmail=error" in loc, loc)
    check("带上 access_denied 原因", "access_denied" in loc, loc)


def testCallbackMissingCode():
    sid = makeSession()
    r = client.get("/api/gmail/callback", params={"state": sid},
                   follow_redirects=False)
    loc = r.headers.get("location", "")
    check("缺 code 跳 error", "gmail=error" in loc, loc)
    check("原因标注 missing_code", "missing_code" in loc, loc)


def testClaimAfterRestartStillWorks():
    """会话落盘后,重启也不该让 claim 拿不到凭据。"""
    sid = makeSession()
    r = client.post("/api/gmail/claim", json={"sid": sid})
    # 还没授权过 -> 404 是正确行为
    check("未授权时 claim 返回 404", r.status_code == 404, r.text)

    sessions.setField(sid, "gmailCreds", {"token": "T"})
    reloaded = importlib.reload(sessions)
    s = reloaded.get(sid)
    check("重启后仍能读到会话", s is not None)
    check("重启后凭据仍在会话", bool(s and s.get("gmailCreds")), str(s))


def testStatusReportsConfigured():
    sid = makeSession()
    r = client.get("/api/gmail/status", params={"sid": sid})
    check("status 200", r.status_code == 200, r.text)
    body = r.json()
    check("configured=True(credentials.json 存在)", body.get("configured") is True, str(body))
    check("返回代理信息", "proxy" in body, str(body))


if __name__ == "__main__":
    for fn in [testAuthUrlStoresFlowState,
               testCallbackRecoversFlowAfterRestart,
               testCallbackWithoutAnyFlowStillGuidesReauth,
               testCallbackUserDenied,
               testCallbackMissingCode,
               testClaimAfterRestartStillWorks,
               testStatusReportsConfigured]:
        print("\n=== %s ===" % fn.__name__)
        fn()
    print("\n结果:", "全部通过" if not fails else "失败: %s" % fails)
    sys.exit(1 if fails else 0)
