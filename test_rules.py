# -*- coding: utf-8 -*-
"""端到端测试规则 API:
   - 创建结构化规则的合法性校验
   - 列出规则
   - 更新优先级
   - 删除
不依赖神象云账号密码,直接连 service store 验证。
"""
import os
import sys
import json
import tempfile
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 使用临时数据库,避免污染真实的 autosui.db
tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
tmp.close()
os.environ["AUTO_SUI_DB"] = tmp.name

from server import store
from server import reconcile


def freshUser():
    # 清空规则,给一个全新的用户
    u = store.getOrCreateUser("test_rules_user")
    with sqlite3.connect(tmp.name) as conn:
        conn.execute("DELETE FROM rules WHERE user_id = ?", (u["id"],))
    return u["id"]


def testAddStructuredRule():
    uid = freshUser()
    rid = store.addRule(uid, {
        "conditions": [{"field": "opAccName", "match": "eq", "value": "测试对手"}],
        "op": "payout",
        "catid": "abc",
        "memo": "测试规则",
        "priority": 50
    })
    assert rid > 0, "addRule 应该返回 id"
    rules = store.listRules(uid)
    assert len(rules) == 1 and rules[0]["priority"] == 50
    print(f"[OK] add + list: id={rid}, priority={rules[0]['priority']}")


def testUpdateRule():
    uid = freshUser()
    rid = store.addRule(uid, {
        "conditions": [{"field": "memo", "match": "contains", "value": "京东"}],
        "op": "payout", "catid": "x", "priority": 10
    })
    ok = store.updateRule(uid, rid, {"priority": 99,
                                    "conditions": [{"field": "memo", "match": "contains", "value": "淘宝"}]})
    assert ok
    rules = store.listRules(uid)
    assert rules[0]["priority"] == 99
    assert json.loads(rules[0]["conditions"])[0]["value"] == "淘宝"
    print("[OK] update priority & conditions")


def testMatchRuleMulti():
    """每条记录的 opAccName 不一致 —— 通过 equals 命中特定规则,contains 命中宽松规则。"""
    ruleEq = {"conditions": [{"field": "opAccName", "match": "eq", "value": "招商银行"}],
              "op": "income", "priority": 100}
    ruleContains = {"conditions": [{"field": "memo", "match": "contains", "value": "京东"}],
                    "op": "payout", "priority": 50}
    d1 = {"opAccName": "招商银行", "memo": "京东支付", "transType": "income"}
    d2 = {"opAccName": "支付宝", "memo": "京东商城", "transType": "payout"}

    # opAccName=招商银行 命中 ruleEq
    matched = reconcile.checkRules([ruleEq, ruleContains], d1)
    assert matched is ruleEq, f"应该命中 eq 规则,实际={matched}"
    # memo 含「京东」命中 ruleContains
    matched = reconcile.checkRules([ruleEq, ruleContains], d2)
    assert matched is ruleContains
    # opAccName 是招商银行,memo 也含「京东」,两条都命中,优先级高的胜出
    matched = reconcile.checkRules([ruleEq, ruleContains], {"opAccName": "招商银行", "memo": "京东支付"})
    assert matched is ruleEq, f"应该命中等优先级最高的 eq 规则"
    print("[OK] 优先级排序 + AND 命中")


def testMatchRuleBadRegex():
    """坏规则不能让整条匹配挂了 —— 异常应当被吞掉。"""
    bad = {"conditions": [{"field": "memo", "match": "regex", "value": "(invalid["}],
           "op": "payout", "priority": 10}
    matched = reconcile.checkRules([bad], {"memo": "anything"})
    assert matched is None, "异常应当被吞,返回 None"
    print("[OK] 异常兜底")


def testMatchRuleEmptyConditions():
    """conditions 为空不能当成万能规则。"""
    empty = {"conditions": [], "op": "payout", "priority": 10}
    matched = reconcile.checkRules([empty], {"memo": "anything"})
    assert matched is None
    print("[OK] 空条件不命中")


def testDeleteRule():
    uid = freshUser()
    r1 = store.addRule(uid, {"conditions": [{"field": "opAccName", "match": "eq", "value": "a"}],
                        "op": "payout"})
    r2 = store.addRule(uid, {"conditions": [{"field": "opAccName", "match": "eq", "value": "b"}],
                        "op": "payout"})
    store.deleteRule(uid, r1)
    rules = store.listRules(uid)
    assert len(rules) == 1 and rules[0]["id"] == r2
    print("[OK] delete")


def testRecordHit():
    uid = freshUser()
    rid = store.addRule(uid, {
        "conditions": [{"field": "opAccName", "match": "eq", "value": "x"}],
        "op": "payout"
    })
    for _ in range(3):
        store.recordRuleHit(uid, rid)
    rules = store.listRules(uid)
    assert rules[0]["hit_count"] == 3
    assert rules[0]["last_hit"]
    print("[OK] hit 累加")


def testStructuredCondWhitelist():
    """expToConditions 只产出白名单里有的字段。"""
    conds = reconcile.expToConditions("opAccName == '张三' and not_in_field == 'bad'")
    assert len(conds) == 1 and conds[0]["field"] == "opAccName"
    print("[OK] expToConditions 白名单过滤")


if __name__ == "__main__":
    testAddStructuredRule()
    testUpdateRule()
    testMatchRuleMulti()
    testMatchRuleBadRegex()
    testMatchRuleEmptyConditions()
    testDeleteRule()
    testRecordHit()
    testStructuredCondWhitelist()
    print("\n所有规则 API 测试通过。")
    os.unlink(tmp.name)
