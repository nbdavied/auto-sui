# -*- coding: utf-8 -*-
"""账本清单（两来源分开取）+ token 登录 + 旧账本切换 回归测试。

按用户对接口的界定，两个来源是各自独立的、互不重叠：
  - 神象云账本 : GET yun.feidee.net/cab-index-ws/v3/book-group/cloud → shenxiang.py
  - 旧随手记   : GET tally.feidee.net/mini_program/v1/books/list      → sui.py

覆盖:
  - 两个 collector 各取各的, provider 标对
  - 任一来源失败不影响另一个;两者皆失败 -> 空清单不抛
  - 登录时两份直接拼接
  - createClientFromToken 不触发密码登录
  - /api/login 用 token 绕过失败的密码登录
  - 旧账本 selectBook 会按 id 真正切换(sui.py 的 switchId 曾是写死的)
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
tmp.close()
os.environ["AUTO_SUI_DB"] = tmp.name

from fastapi.testclient import TestClient                              # noqa: E402
from server import sui_service                                         # noqa: E402
from server.main import (app, _collectShenxiangBooks, _collectLegacyBooks,  # noqa: E402
                         PROVIDER_SHENXIANG, PROVIDER_LEGACY)

client = TestClient(app)


class BooksFixture:
    """可控的假 client:两个账本源能单独摆布,互不影响。"""
    def __init__(self, native=None, legacy=None,
                 nativeErr=None, legacyErr=None):
        self._native = native if native is not None else []
        self._legacy = legacy if legacy is not None else []
        self._nativeErr = nativeErr
        self._legacyErr = legacyErr

    def getBooks(self):
        if self._nativeErr:
            raise self._nativeErr
        return list(self._native)

    def listAllBooks(self):
        if self._legacyErr:
            raise self._legacyErr
        return list(self._legacy)


SHENXIANG = [
    {"id": "1183356777640235009", "name": "测试账本"},
    {"id": "1183356777640235010", "name": "家庭账本"},
]
LEGACY = [
    {"id": "1505498391", "name": "2015-", "raw": {}},
    {"id": "1752598474", "name": "2012-2014", "raw": {}},
]


def testShenxiangBooksMarkedCorrectly():
    fake = BooksFixture(native=SHENXIANG, legacy=LEGACY)
    books = _collectShenxiangBooks(fake, "u@e.com")
    assert len(books) == 2, books
    # 神象云那份只该有神象云的,不能把旧账本混进来
    assert {b["id"] for b in books} == {"1183356777640235009",
                                        "1183356777640235010"}
    assert all(b["provider"] == PROVIDER_SHENXIANG for b in books)
    print("[OK] 神象云 collector 只取神象云账本")


def testLegacyBooksMarkedCorrectly():
    fake = BooksFixture(native=SHENXIANG, legacy=LEGACY)
    books = _collectLegacyBooks(fake, "u@e.com")
    assert len(books) == 2, books
    assert {b["id"] for b in books} == {"1505498391", "1752598474"}
    # books/list 拿到的旧账本必须用 sui.py 操作
    assert all(b["provider"] == PROVIDER_LEGACY for b in books)
    print("[OK] 旧账本 collector 标为 legacy(走 sui.py)")


def testNamesPreserved():
    """books/list 给的是真实账本名,不能被覆盖成占位名。"""
    fake = BooksFixture(native=SHENXIANG, legacy=LEGACY)
    books = _collectLegacyBooks(fake, "u@e.com")
    assert {b["name"] for b in books} == {"2015-", "2012-2014"}
    print("[OK] 保留 books/list 返回的真实账本名")


def testSourcesIndependentOnFailure():
    """一个源挂掉,另一个照常返回 —— 两者互不依赖。"""
    fake = BooksFixture(native=SHENXIANG, legacyErr=RuntimeError("401"))
    sx = _collectShenxiangBooks(fake, "u@e.com")
    lg = _collectLegacyBooks(fake, "u@e.com")
    assert len(sx) == 2, "神象云源不该受旧账本源影响"
    assert lg == [], "旧账本源失败应返回空而不是抛"

    fake2 = BooksFixture(nativeErr=RuntimeError("500"), legacy=LEGACY)
    sx2 = _collectShenxiangBooks(fake2, "u@e.com")
    lg2 = _collectLegacyBooks(fake2, "u@e.com")
    assert sx2 == []
    assert len(lg2) == 2, "旧账本源不该受神象云源影响"
    print("[OK] 两个来源互不影响,失败各自降级")


def testBothFailGivesEmpty():
    fake = BooksFixture(nativeErr=RuntimeError("a"), legacyErr=RuntimeError("b"))
    assert _collectShenxiangBooks(fake, "u@e.com") == []
    assert _collectLegacyBooks(fake, "u@e.com") == []
    print("[OK] 两源皆失败返回空清单,不抛")


def testMalformedEntriesSkipped():
    """缺 id 的脏数据要跳过,不能污染列表。"""
    fake = BooksFixture(native=[{"id": "", "name": "空"},
                                {"id": "WRAP", "name": None}],
                        legacy=[])
    books = _collectShenxiangBooks(fake, "u@e.com")
    assert [b["id"] for b in books] == ["WRAP"], books
    assert books[0]["name"] == "WRAP", "name 缺失时用 id 兜底"
    print("[OK] 脏数据被跳过")


def testCreateClientFromTokenSkipsPasswordLogin():
    """token 方式不应触发密码登录(否则风控期照样 4099)。"""
    calls = []

    class FakeSx:
        def __init__(self, cfg):
            calls.append(("init", cfg))

        def login(self):
            calls.append(("login",))

        def setToken(self, tok, tokenType="Bearer"):
            calls.append(("setToken", tok))

    saved = sui_service.ShenxiangClient
    sui_service.ShenxiangClient = FakeSx
    try:
        sui_service.createClientFromToken("  tok-abc  ")
    finally:
        sui_service.ShenxiangClient = saved

    kinds = [c[0] for c in calls]
    assert "login" not in kinds, "token 模式绝不能调 login()"
    assert calls[-1][1] == "tok-abc", "token 需要 strip 掉首尾空白"
    print("[OK] createClientFromToken 不触发密码登录且 trim token")


def testLoginConcatenatesBothSources():
    """登录后账本清单 = 神象云 + 旧账本两份拼接。"""
    class FakeSx:
        def __init__(self, cfg):
            pass

        def login(self):
            raise RuntimeError("登录失败: {'code': 4099}")

        def setToken(self, tok, tokenType="Bearer"):
            pass

        def getBooks(self):
            return list(SHENXIANG)

        def listAllBooks(self):
            return list(LEGACY)

    from server import sui_service as ss, legacy_sui_service as lb
    savedSx, savedLegacyCreate = ss.ShenxiangClient, lb.createClient
    ss.ShenxiangClient = FakeSx
    lb.createClient = lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("login.sui.com 不可用"))
    try:
        r = client.post("/api/login", json={
            "username": "u5@e.com", "password": "whatever",
            "shenxiangToken": "tok-123"})
    finally:
        ss.ShenxiangClient = savedSx
        lb.createClient = savedLegacyCreate

    assert r.status_code == 200, r.text
    books = r.json()["books"]
    assert len(books) == 4, books
    sx = [b for b in books if b["provider"] == PROVIDER_SHENXIANG]
    lg = [b for b in books if b["provider"] == PROVIDER_LEGACY]
    assert len(sx) == 2 and len(lg) == 2, books
    # 没有重复项
    assert len({b["id"] for b in books}) == 4
    print("[OK] 两份来源拼接成 4 个账本,无重复")


def testLoginPasswordFailureStillNeedsToken():
    """没给 token 时密码登录失败仍要 400,并提示可用 token。"""
    saved = sui_service.createClient

    def boom(u, p):
        raise RuntimeError("登录失败: {'code': 4099}")
    sui_service.createClient = boom
    try:
        r = client.post("/api/login", json={"username": "u6@e.com",
                                            "password": "x"})
    finally:
        sui_service.createClient = saved
    assert r.status_code == 400
    assert "access_token" in r.json()["detail"], "错误要告诉用户还有 token 这条路"
    print("[OK] 无 token 时密码失败仍 400,且提示 token 旁路")


def testSelectBookSwitchesLegacyTarget():
    """选第二个旧账本时,sui.py 必须被切到那个 id 并重拉账户/分类。

    sui.py 里 switchId 原先写死成默认账本,第二个旧账本根本进不去。
    """
    calls = []

    class FakeSui:
        def initTallyInfo(self, bookId=None):
            calls.append(bookId)

    from server import legacy_sui_service as lb
    saved = lb.buildAccountOptions, lb.buildCategoryOptions
    lb.buildAccountOptions = lambda c: []
    lb.buildCategoryOptions = lambda c: {"income": [], "payout": []}
    try:
        lb.selectBook(FakeSui(), "1752598474")
    finally:
        lb.buildAccountOptions, lb.buildCategoryOptions = saved

    assert calls == ["1752598474"], f"应切到目标账本,实际 {calls}"
    print("[OK] selectBook 切换到指定旧账本 id")


def testSelectBookDefaultsWhenNoId():
    fake_calls = []

    class FakeSui:
        def initTallyInfo(self, bookId=None):
            fake_calls.append(bookId)

    from server import legacy_sui_service as lb
    saved = lb.buildAccountOptions, lb.buildCategoryOptions
    lb.buildAccountOptions = lambda c: []
    lb.buildCategoryOptions = lambda c: {"income": [], "payout": []}
    try:
        lb.selectBook(FakeSui(), "")
    finally:
        lb.buildAccountOptions, lb.buildCategoryOptions = saved
    assert fake_calls == [lb.LEGACY_BOOK_ID], fake_calls
    print("[OK] 未指定 id 时回落到默认账本")


def testSelectBookRejectsMissingClient():
    from server import legacy_sui_service as lb
    try:
        lb.selectBook(None, "1752598474")
    except RuntimeError as e:
        assert "未登录" in str(e)
        print("[OK] 无 client 时拒绝切换")
        return
    raise AssertionError("应抛 RuntimeError")


if __name__ == "__main__":
    testShenxiangBooksMarkedCorrectly()
    testLegacyBooksMarkedCorrectly()
    testNamesPreserved()
    testSourcesIndependentOnFailure()
    testBothFailGivesEmpty()
    testMalformedEntriesSkipped()
    testCreateClientFromTokenSkipsPasswordLogin()
    testLoginConcatenatesBothSources()
    testLoginPasswordFailureStillNeedsToken()
    testSelectBookSwitchesLegacyTarget()
    testSelectBookDefaultsWhenNoId()
    testSelectBookRejectsMissingClient()
    print("\n账本清单 + token 登录 + 旧账本切换测试通过。")
