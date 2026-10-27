# -*- coding: utf-8 -*-
"""对账去重回归测试: 一条账本流水只能证明一笔银行流水已入账。

场景(用户 2026-10 报的 bug):
  银行账单 10-05 有两笔 5.00 元支出,账本里只记了一条。
  修复前这两条银行流水都拿去和同一条账本流水比对,双双命中 →
  两条都显示「已入账」,其中一笔实际漏记却完全看不出来。
  正确行为: 第一条 matched,第二条按规则走 auto / manual。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from server import reconcile

SUIID = "acc_1"


def suiDetail(tranId, sdate, amount, tranType=1, accountId=SUIID):
    """构造一条账本流水(支出 tranType=1,收入 5,转账 2)。"""
    d = {
        "tranId": tranId,
        "sdate": sdate,
        "itemAmount": amount,
        "tranType": tranType,
    }
    if tranType == 2:
        d["buyerAcountId"] = accountId
        d["sellerAcountId"] = "other"
    return d


def bankDetail(date, amount, transType="payout"):
    return {
        "date": date,
        "time": "",
        "amount": amount,
        "transType": transType,
        "opAccNo": "",
        "opAccName": "",
        "usage": "",
        "memo": "测试",
    }


def testTwoSameExpensesOnlyOneMatched():
    banks = [bankDetail("20261005", "5.00"), bankDetail("20261005", "5.00")]
    suis = [suiDetail("t1", "20261005", 5.0)]
    items = reconcile.reconcileDetails(banks, suis, SUIID, [])

    assert items[0]["status"] == "matched", items
    assert items[1]["status"] != "matched", items[1]
    # 第二条没规则命中,必须落到人工判断,而不是被静默标成已入账
    assert items[1]["status"] == "manual", items[1]
    print("[OK] 同日同额两笔支出,只有一条被判已入账")


def testTwoSameExpensesTwoSuiRecordsBothMatched():
    """账本确实记了两条时,两条银行流水都应判已入账(不能过度去重)。"""
    banks = [bankDetail("20261005", "5.00"), bankDetail("20261005", "5.00")]
    suis = [suiDetail("t1", "20261005", 5.0), suiDetail("t2", "20261005", 5.0)]
    items = reconcile.reconcileDetails(banks, suis, SUIID, [])
    assert [i["status"] for i in items] == ["matched", "matched"]
    # 不能两条都挂在同一条账本流水上
    assert items[0]["matched"]["tranId"] != items[1]["matched"]["tranId"]
    print("[OK] 账本有两条时两条都判已入账,且各自对应不同流水")


def testThirdDuplicateGoesManual():
    banks = [bankDetail("20261005", "5.00") for _ in range(3)]
    suis = [suiDetail("t1", "20261005", 5.0), suiDetail("t2", "20261005", 5.0)]
    items = reconcile.reconcileDetails(banks, suis, SUIID, [])
    assert [i["status"] for i in items] == ["matched", "matched", "manual"]
    print("[OK] 3 笔银行 + 2 笔账本 -> 2 matched + 1 manual")


def testDuplicateWithRuleGoesAuto():
    """第二条未入账的流水若命中规则,应给 auto,可以直接一键记账。"""
    rules = [{
        "priority": 0,
        "conditions": [{"field": "amount", "match": "eq", "value": "5.00"},
                       {"field": "transType", "match": "eq", "value": "payout"}],
    }]
    banks = [bankDetail("20261005", "5.00"), bankDetail("20261005", "5.00")]
    suis = [suiDetail("t1", "20261005", 5.0)]
    items = reconcile.reconcileDetails(banks, suis, SUIID, rules)
    assert items[0]["status"] == "matched"
    assert items[1]["status"] == "auto", items[1]
    assert items[1]["rule"] is not None
    print("[OK] 第二条未入账且命中规则 -> auto")


def testDifferentAmountsUnaffected():
    banks = [bankDetail("20261005", "5.00"), bankDetail("20261005", "6.00")]
    suis = [suiDetail("t1", "20261005", 5.0)]
    items = reconcile.reconcileDetails(banks, suis, SUIID, [])
    assert [i["status"] for i in items] == ["matched", "manual"]
    print("[OK] 金额不同的条目不受去重影响")


def testIncomeAndTransferStillMatch():
    """去重改动不能影响收入/转账的匹配语义。"""
    banks = [bankDetail("20261005", "88.00", "income")]
    suis = [suiDetail("t1", "20261005", 88.0, tranType=5)]
    items = reconcile.reconcileDetails(banks, suis, SUIID, [])
    assert items[0]["status"] == "matched"

    tbanks = [bankDetail("20261005", "200.00", "payout")]
    tsuis = [suiDetail("t2", "20261005", 200.0, tranType=2)]
    items = reconcile.reconcileDetails(tbanks, tsuis, SUIID, [])
    assert items[0]["status"] == "matched"
    print("[OK] 收入/转账匹配语义不变")


if __name__ == "__main__":
    testTwoSameExpensesOnlyOneMatched()
    testTwoSameExpensesTwoSuiRecordsBothMatched()
    testThirdDuplicateGoesManual()
    testDuplicateWithRuleGoesAuto()
    testDifferentAmountsUnaffected()
    testIncomeAndTransferStillMatch()
    print("\n全部通过")
