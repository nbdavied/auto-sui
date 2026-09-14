# -*- coding: utf-8 -*-
"""端到端 HTTP 测试: 验证 validateConditions 拦截坏规则的逻辑。

绕过登录,直接调 FastAPI app 内部的函数,确认:
  - 合法条件能过
  - 未知字段/匹配方式被 400
  - 缺失值被 400
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 用临时 DB 隔离
tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
tmp.close()
os.environ["AUTO_SUI_DB"] = tmp.name

from fastapi.testclient import TestClient
from server import store
from server.main import app, validateConditions

client = TestClient(app)


def testValidateOk():
    out = validateConditions([{"field": "opAccName", "match": "eq", "value": "对手"}])
    assert out[0]["field"] == "opAccName"
    print("[OK] 合法条件通过")


def testValidateBadField():
    from fastapi import HTTPException
    raised = False
    try:
        validateConditions([{"field": "__import__", "match": "eq", "value": "x"}])
    except HTTPException as e:
        raised = True
        assert e.status_code == 400
    assert raised, "未知字段应抛 400"
    print("[OK] 未知字段拦截")


def testValidateBadMatch():
    from fastapi import HTTPException
    raised = False
    try:
        validateConditions([{"field": "opAccName", "match": "eval", "value": "x"}])
    except HTTPException as e:
        raised = True
        assert e.status_code == 400
    assert raised
    print("[OK] 未知匹配方式拦截")


def testValidateEmpty():
    from fastapi import HTTPException
    raised = False
    try:
        validateConditions([{"field": "opAccName", "match": "eq", "value": "  "}])
    except HTTPException as e:
        raised = True
        assert e.status_code == 400
    assert raised
    print("[OK] 空值拦截")


def testValidateEmptyList():
    from fastapi import HTTPException
    raised = False
    try:
        validateConditions([])
    except HTTPException as e:
        raised = True
    assert raised
    print("[OK] 空数组拦截")


def testHttpAddRuleWithoutSid():
    """缺少 sid 应 401/422。"""
    r = client.post("/api/rules", json={
        "conditions": [{"field": "opAccName", "match": "eq", "value": "x"}],
        "op": "payout"
    })
    # 没 sid 会 422(pydantic 校验) 或 401(中间件),都通过
    assert r.status_code in (401, 422)
    print(f"[OK] 无 sid 被拦 ({r.status_code})")


if __name__ == "__main__":
    testValidateOk()
    testValidateBadField()
    testValidateBadMatch()
    testValidateEmpty()
    testValidateEmptyList()
    testHttpAddRuleWithoutSid()
    print("\n所有 HTTP 校验测试通过。")
