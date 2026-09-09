# -*- coding: utf-8 -*-
"""端到端验证: 单账户「记账 -> 查流水 -> 去重匹配」闭环。

验证目标:
  1. 用 conf.json 里第一个账户(1211)记一笔支出
  2. 从账本拉流水
  3. 用 run.py 的去重逻辑 findSuiDetail 验证:
     - 刚记的这笔能被匹配到(不会重复记账)
     - 不存在的金额不会被误匹配(不会漏记账)
"""
import sys
from datetime import datetime

from configReader import readConfig
from shenxiang import ShenxiangClient
import run

TEST_AMOUNT = "0.07"
TEST_MEMO = "自动记账测试-去重验证"
# 时间兜底验证用的过去日期(只有日期、无时间)
PAST_DATE = "2026-09-01"
PAST_AMOUNT = "0.08"


def main():
    config = readConfig()
    account = config["accounts"][0]
    suiid = account["suiid"]
    print("测试账户: %s -> %s (%s)" % (account["bankno"], suiid, account["type"]))

    client = ShenxiangClient(config)
    client.login()
    client.initTallyInfo()

    today = datetime.now()
    dateStr = today.strftime("%Y%m%d")
    payTime = today.strftime("%Y-%m-%d %H:%M")
    beginDate = today.strftime("%Y.%m.%d")
    endDate = today.strftime("%Y.%m.%d")

    # 1. 记账
    print("\n--- 步骤1: 记一笔支出 %s ---" % TEST_AMOUNT)
    cats = client.getCategories()
    payoutCats = cats["payout"]
    if not payoutCats:
        print("无支出分类,终止")
        return
    firstCat = payoutCats[0]
    catId = firstCat["subCat"][0]["id"] if firstCat["subCat"] else firstCat["id"]
    print("使用分类: %s / %s" % (firstCat["name"], catId))
    r = client.payout(suiid, TEST_AMOUNT, catId, payTime=payTime, memo=TEST_MEMO)
    if r.status_code not in (200, 201):
        print("记账失败,终止")
        return

    # 2. 查流水
    print("\n--- 步骤2: 查询账户流水 (%s ~ %s) ---" % (beginDate, endDate))
    details = client.accountDetail(suiid, beginDate, endDate)
    print("流水条数: %d" % len(details))
    for d in details:
        print("   ", d)

    # 3. 去重匹配验证
    print("\n--- 步骤3: 去重匹配验证 ---")
    bankDetailHit = {
        "date": dateStr, "time": "120000", "amount": TEST_AMOUNT,
        "transType": "payout", "opAccNo": "", "opAccName": "",
        "usage": "", "memo": TEST_MEMO,
    }
    matched = run.findSuiDetail(bankDetailHit, details, suiid)
    print("[用例A] 已记账金额 %s -> %s" % (
        TEST_AMOUNT, "命中(正确:不会重复记账)" if matched else "未命中(错误!)"))

    bankDetailMiss = dict(bankDetailHit, amount="99.99")
    matched2 = run.findSuiDetail(bankDetailMiss, details, suiid)
    print("[用例B] 未记账金额 99.99 -> %s" % (
        "未命中(正确:会触发记账)" if matched2 is None else "命中(错误!会漏记)"))

    # 4. 转账方向验证
    print("\n--- 步骤4: 转账方向验证 ---")
    transfers = [d for d in details if d["tranType"] == 2]
    if transfers:
        t = transfers[0]
        print("样本转账: from=%s to=%s amount=%s" % (
            t["buyerAcountId"], t["sellerAcountId"], t["itemAmount"]))
    else:
        print("今日无转账流水(之前测试记的转账不在此区间,可忽略)")

    # 5. 时间兜底端到端验证: 过去日期 + 无时间 -> 必须记到该日期 08:00
    print("\n--- 步骤5: 时间兜底验证(日期 %s, 无时间) ---" % PAST_DATE)
    payTimePast = run.buildPayTime(PAST_DATE.replace("-", ""), "")
    print("构造的 payTime:", payTimePast)
    r = client.payout(suiid, PAST_AMOUNT, catId, payTime=payTimePast,
                      memo="自动记账测试-时间兜底")
    if r.status_code in (200, 201):
        pastDetails = client.accountDetail(suiid, "2026.09.01", "2026.09.01")
        hit = [d for d in pastDetails
               if format(d["itemAmount"], "0.2f") == PAST_AMOUNT and d["tranType"] == 1]
        print("该日流水条数: %d, 命中测试笔: %s" % (len(pastDetails), bool(hit)))
        print("[用例C] 无时间条目 -> %s" % (
            "落到 %s(正确)" % PAST_DATE if hit else "未落到目标日期(错误!)"))
    else:
        print("时间兜底记账失败:", r.status_code, r.text[:200])

    print("\n验证结束。测试账本中本次新增 2 笔(%s / %s),用完可手动删除。"
          % (TEST_AMOUNT, PAST_AMOUNT))


if __name__ == "__main__":
    main()
