# -*- coding: utf-8 -*-
"""多 provider 切换回归测试。

  - legacy_sui_service.listBooks 形态正确
  - /api/login 把神象云账本打上 provider 标签;旧账本连不上时优雅降级
  - /api/book 接受 provider 并切换激活的 client
  - /api/tally 按 provider 路由(legacy 走 sui.py,shenxiang 走 client.payout/...)
  - _normalizeLegacyDetails 把旧体系的 raw 数据归一化成对账引擎可读
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
tmp.close()
os.environ["AUTO_SUI_DB"] = tmp.name

from contextlib import contextmanager
from fastapi.testclient import TestClient
from server import legacy_sui_service
from server import sui_service
from server.main import app, _normalizeLegacyDetails

client = TestClient(app)


@contextmanager
def patch(**kwargs):
    """轻量 monkeypatch: 把 server.x.y.z 路径的属性替换,推出 with 时还原。

    调用:patch(sui_service_createClient=..., legacy_sui_service_xxx=...) 太丑,
    改成接 kwargs={'full.dotted.path': value}。内部去掉拼接 root。
    """
    saved = {}
    try:
        for dotted, value in kwargs.items():
            parts = dotted.split(".")
            obj = sys.modules[parts[0]]
            for piece in parts[1:]:
                obj = getattr(obj, piece)
            saved[dotted] = obj
            # 重新走一遍拿到顶层,因为 obj 上面被改成了 next-level
            top = sys.modules[parts[0]]
            for piece in parts[1:-1]:
                top = getattr(top, piece)
            setattr(top, parts[-1], value)
        yield
    finally:
        for dotted, value in saved.items():
            parts = dotted.split(".")
            top = sys.modules[parts[0]]
            for piece in parts[1:-1]:
                top = getattr(top, piece)
            setattr(top, parts[-1], value)


# --------------------------------------------------------------------- #
# legacy_sui_service 静态字段
# --------------------------------------------------------------------- #
def testListBooks():
    books = legacy_sui_service.listBooks()
    assert len(books) == 1
    b = books[0]
    assert b["provider"] == "legacy"
    assert b["name"] == "旧随手记账本"
    assert b["id"] == "1505498391"
    print("[OK] listBooks 返回标准账本")


def testNormalizeLegacyDetailsEmpty():
    assert _normalizeLegacyDetails([]) == []
    assert _normalizeLegacyDetails(None) == []
    print("[OK] 归一化空输入安全")


def testNormalizeLegacyDetailsAlreadyShaped():
    """归一化对已是 shenxiang 形态的数据不会改写,直接透传。"""
    src = [{"sdate": "20250103", "itemAmount": 14.9, "tranType": 1,
            "sellerAcountId": "a", "buyerAcountId": "b", "tranId": "tx_001"}]
    out = _normalizeLegacyDetails(src)
    assert out[0]["sdate"] == "20250103"
    assert out[0]["itemAmount"] == 14.9
    print("[OK] shenxiang 形态透传")


def testNormalizeLegacyDetailsFuzzyMapping():
    """旧体系 detail 可能用 price/money 等字段,归一化要做宽容映射。"""
    src = [{
        "sdate": "20250103",
        "price": "12.50",
        "inoutType": 1,
        "sellerAccountId": "x",
        "buyerAccountId": "y",
        "id": "tx_9"
    }]
    out = _normalizeLegacyDetails(src)
    d = out[0]
    assert d["itemAmount"] == 12.5, "应兼容字符串金额"
    assert d["tranType"] == 1
    assert d["sellerAcountId"] == "x"
    assert d["buyerAcountId"] == "y"
    assert d["tranId"] == "tx_9"
    print("[OK] 模糊字段归一化")


def testNormalizeLegacyDetailsMissingFields():
    """字段不全也不会抛 —— 让 reconcile 当 unmatched 处理而不是 5xx。"""
    src = [{"sdate": "", "foo": "bar"}]
    out = _normalizeLegacyDetails(src)
    d = out[0]
    assert d["itemAmount"] == 0.0
    assert d["tranType"] == 0
    print("[OK] 缺字段兜底为 0,归一化不抛")


# --------------------------------------------------------------------- #
# /api/login 多 provider 行为
# --------------------------------------------------------------------- #
class FakeShenxiang:
    def __init__(self, books):
        self._books = books
    def getBooks(self):
        return list(self._books)
    def setBookId(self, *a, **kw): pass
    def initTallyInfo(self, *a, **kw): pass


def testLoginReturnsProviderForEachBook():
    with patch(**{
        "server.sui_service.createClient": lambda u, p: FakeShenxiang([
            {"id": "X1", "name": "账本A"},
            {"id": "X2", "name": "账本B"},
        ]),
        "server.legacy_sui_service.createClient": lambda u, p: object(),
    }):
        r = client.post("/api/login", json={"username": "u@e.com", "password": "x"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    providers = [b["provider"] for b in data["books"]]
    assert providers == ["shenxiang", "shenxiang", "legacy"]
    assert data["provider"] in ("shenxiang", "legacy")
    print("[OK] /api/login 给每个账本打 provider 标签")


def testLoginLegacyFailsDoesNotBlock():
    """旧体系登录失败 -> 旧账本选项不出现,但 login 仍 200。"""
    def boom(u, p):
        raise Exception("login.sui.com 502")
    with patch(**{
        "server.sui_service.createClient": lambda u, p: FakeShenxiang([{"id": "X1", "name": "账本A"}]),
        "server.legacy_sui_service.createClient": boom,
    }):
        r = client.post("/api/login", json={"username": "u2@e.com", "password": "x"})
    assert r.status_code == 200
    data = r.json()
    assert len(data["books"]) == 1
    assert data["books"][0]["provider"] == "shenxiang"
    print("[OK] 旧体系失败时优雅降级,不阻塞登录")


def testLoginShenxiangFailsIsFatal():
    """新体系登录失败应当直接 400,不能「没有账本也登录成功」。"""
    def boom(u, p):
        raise Exception("神象云挂了")
    with patch(**{
        "server.sui_service.createClient": boom,
    }):
        r = client.post("/api/login", json={"username": "u3@e.com", "password": "x"})
    assert r.status_code == 400
    print("[OK] 新体系失败时硬拦 400")


# --------------------------------------------------------------------- #
# /api/book 接受 provider
# --------------------------------------------------------------------- #
def testSelectBookLegacyWithoutLegacyClientRejected():
    """会话没有 legacyClient(legacy 登录失败过),切到 legacy 应当 400。"""
    with patch(**{
        "server.sui_service.createClient": lambda u, p: FakeShenxiang([{"id": "X1", "name": "账本A"}]),
        "server.legacy_sui_service.createClient":
            lambda u, p: (_ for _ in ()).throw(Exception("legacy 挂")),
    }):
        r = client.post("/api/login", json={"username": "u4@e.com", "password": "x"})
    sid = r.json()["sid"]
    r = client.post("/api/book",
                    json={"sid": sid, "bookId": legacy_sui_service.LEGACY_BOOK_ID,
                          "provider": "legacy"})
    assert r.status_code == 400
    print("[OK] legacy 不可用时拒绝切换")


def testSelectBookUnknownProviderRejected():
    """provider 不在白名单返回 400。"""
    with patch(**{
        "server.sui_service.createClient": lambda u, p: FakeShenxiang([{"id": "X1", "name": "A"}]),
        "server.legacy_sui_service.createClient":
            lambda u, p: (_ for _ in ()).throw(Exception("x")),
    }):
        r = client.post("/api/login", json={"username": "u5@e.com", "password": "x"})
    sid = r.json()["sid"]
    r = client.post("/api/book", json={"sid": sid, "bookId": "X1",
                                       "provider": "something_bad"})
    assert r.status_code == 400
    print("[OK] provider 不在白名单被 400")


# --------------------------------------------------------------------- #
# /api/tally 按 provider 路由
# --------------------------------------------------------------------- #
class CountingLegacy:
    """能记录每次被调用的服务对象。"""
    def __init__(self):
        self.calls = []
    def payout(self, *a, **kw):
        self.calls.append(("payout", a, kw))
    def income(self, *a, **kw):
        self.calls.append(("income", a, kw))
    def transfer(self, *a, **kw):
        self.calls.append(("transfer", a, kw))


def testTallyRoutesToLegacy():
    """legacy 路径下 payout 应当调 CountingLegacy.payout 而非 shenxiang client。"""
    fake_lex = CountingLegacy()
    fake_shx = FakeShenxiang([{"id": "X1", "name": "A"}])
    with patch(**{
        "server.sui_service.createClient": lambda u, p: fake_shx,
        "server.legacy_sui_service.createClient": lambda u, p: fake_lex,
    }):
        r = client.post("/api/login", json={"username": "u6@e.com", "password": "x"})
    sid = r.json()["sid"]
    # 切到 legacy
    r = client.post("/api/book",
                    json={"sid": sid,
                          "bookId": legacy_sui_service.LEGACY_BOOK_ID,
                          "provider": "legacy"})
    assert r.status_code == 200, r.text
    # 准备 pending 然后调 tally
    from server import session_store as ss
    sess = ss.get(sid)
    sess["pending"] = {
        "source": "upload", "bankno": "622848****1211",
        "startDate": "20260101", "endDate": "20260131",
        "details": [{"amount": 14.9, "date": "20260105", "time": "0800",
                     "transType": "payout", "memo": "测试"}],
        "suiid": legacy_sui_service.LEGACY_BOOK_ID
    }
    r = client.post("/api/tally", json={
        "sid": sid, "suiid": "17330926177",
        "index": 0, "op": "payout",
        "catid": "51160931276", "memo": "auto"
    })
    assert r.status_code == 200, r.text
    assert fake_lex.calls, "legacy 应该收到 payout 调用"
    op_name, args, kw = fake_lex.calls[0]
    assert op_name == "payout"
    assert args[1] == 14.9
    assert kw["memo"] == "auto"
    print("[OK] /api/tally 走 legacy 服务")


if __name__ == "__main__":
    testListBooks()
    testNormalizeLegacyDetailsEmpty()
    testNormalizeLegacyDetailsAlreadyShaped()
    testNormalizeLegacyDetailsFuzzyMapping()
    testNormalizeLegacyDetailsMissingFields()
    testLoginReturnsProviderForEachBook()
    testLoginLegacyFailsDoesNotBlock()
    testLoginShenxiangFailsIsFatal()
    testSelectBookLegacyWithoutLegacyClientRejected()
    testSelectBookUnknownProviderRejected()
    testTallyRoutesToLegacy()
    print("\n多 provider 切换测试通过。")

