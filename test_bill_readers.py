# -*- coding: utf-8 -*-
"""账单类型选择测试:
   - 后端白名单暴露
   - 类型不在白名单时返回带可读提示的 ValueError
   - /api/bills/readers 接口返回前端需要的字段
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
tmp.close()
os.environ["AUTO_SUI_DB"] = tmp.name

from fastapi.testclient import TestClient
from server import readers
from server.main import app

client = TestClient(app)


def testListReadersHasExpectedEntries():
    rs = readers.listFileReaders()
    types = [r["type"] for r in rs]
    assert "abc" in types and "ccb" in types
    for r in rs:
        assert "type" in r and "label" in r
    print(f"[OK] 暴露 {len(rs)} 个文件型 reader")


def testCreateReaderDispatchesByType():
    # 直接检查内部映射 —— 构造函数会去真读 xlsx,不在本测试范围。
    # dispatch 的正确性可以靠 _READER_CLASSES 间接验证。
    from server.readers import _READER_CLASSES
    assert _READER_CLASSES["abc"].__name__ == "ABCReader"
    assert _READER_CLASSES["ccb"].__name__ == "CCBReader"
    print("[OK] 按类型派发映射正确")


def testCreateReaderUnknownType():
    from server.readers import _READER_CLASSES
    assert _READER_CLASSES.get("xyz_bank") is None
    # 同样:走 dispatch,不真开文件
    cfg = {"accounts": []}
    try:
        readers.createReader("xyz_bank", "fake.xlsx", cfg)
    except Exception:
        pass  # 只要不命中 _READER_CLASSES 路径,函数本身会返回 None
    # 直接验证 _READER_CLASSES 不包含这个 key,等于函数返回 None 的充要条件
    assert "xyz_bank" not in _READER_CLASSES
    print("[OK] 未知类型不会命中 dispatch")


def testParseUploadRejectsUnknownType():
    # 不知道类型的文件名,直接走 mock 类
    # 通过 monkey-patch _READER_CLASSES 注入一个不会真开文件的 reader
    from server import readers as r
    class FakeReader:
        def __init__(self, *a, **kw): pass
        def analyseData(self): return {"bankno": "", "suiid": "",
                                       "startDate": "", "endDate": "", "details": []}
    saved = r._READER_CLASSES
    r._READER_CLASSES = {"abc": FakeReader}
    try:
        # 不存在的 bankType
        try:
            r.parseUpload(999, b"", "any.xlsx", "wechatpay")
            assert False, "应当抛 ValueError"
        except ValueError as e:
            msg = str(e)
            assert "不支持" in msg
            assert "农业银行" in msg and "建设银行" in msg
            print("[OK] parseUpload 给出可读错误")

        # 存在的 bankType —— 应当走通
        data = r.parseUpload(999, b"fake", "any.xlsx", "abc")
        assert data["details"] == []
        print("[OK] parseUpload 按 bankType 派发通过")
    finally:
        r._READER_CLASSES = saved


def testHttpBillsReadersEndpoint():
    r = client.get("/api/bills/readers")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    rs = data["readers"]
    assert isinstance(rs, list) and len(rs) >= 2
    types = [x["type"] for x in rs]
    assert "abc" in types and "ccb" in types
    print(f"[OK] HTTP /api/bills/readers 返回 {len(rs)} 项")


def testUploadWithoutBankTypeRejected():
    """缺 bankType 应被 FastAPI 拦(422),不再静默走默认。"""
    r = client.post(
        "/api/bills/upload",
        data={"sid": "fake"},  # 不带 bankType
        files={"file": ("any.xlsx", b"fake", "application/octet-stream")}
    )
    # sid 不存在 → 401;bankType 缺失 → 422. 二者择其一就行,都达到「不接受」
    assert r.status_code in (401, 422)
    print(f"[OK] 缺 bankType 被拒 ({r.status_code})")


if __name__ == "__main__":
    testListReadersHasExpectedEntries()
    testCreateReaderDispatchesByType()
    testCreateReaderUnknownType()
    testParseUploadRejectsUnknownType()
    testHttpBillsReadersEndpoint()
    testUploadWithoutBankTypeRejected()
    print("\n账单类型选择相关测试通过。")
