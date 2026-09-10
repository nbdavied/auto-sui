# -*- coding: utf-8 -*-
"""诊断旧随手记(sui.py)的记账是否真的写进账本。

sui.py 的 payout/income/transfer 只 print 响应,不返回也不校验,
所以「服务端拒绝了」在调用方看来也是成功。这里直接读流水线做前后对比,
把真实结果暴露出来。
"""
import json
import os
import sys
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sui import Sui  # noqa: E402

BOOK = os.environ.get("PROBE_BOOK", "1752598474")
AMOUNT = os.environ.get("PROBE_AMOUNT", "0.01")

conf = json.load(open("conf.json", encoding="utf-8"))
s = Sui({"username": conf["username"], "password": conf["password"]})
s.login()
s.initTallyInfo(BOOK)

accounts = getattr(s, "_Sui__accounts", []) or []
pays = getattr(s, "_Sui__payoutCategories", []) or []
incs = getattr(s, "_Sui__incomeCategories", []) or []
print("账本", BOOK, "账户数", len(accounts))
acc = accounts[0]
print("目标账户", acc)
cat = pays[0]["subCat"][0] if pays and pays[0].get("subCat") else None
icat = incs[0]["subCat"][0] if incs and incs[0].get("subCat") else None
print("支出分类", cat, "收入分类", icat)

today = datetime.date.today()
dstr = today.strftime("%Y.%m.%d")
rstr = today.strftime("%Y.%m.%d")
print("查询区间", dstr, "~", rstr)


def snap(tag):
    try:
        ds = s.accountDetail(acc["id"], dstr, rstr)
    except Exception as e:
        print(f"[{tag}] accountDetail 异常: {e}")
        return []
    print(f"[{tag}] 该账户今日流水 {len(ds)} 条")
    for d in ds:
        print("   ", d.get("tranId"), d.get("tranType"), d.get("itemAmount"),
              d.get("memo"), d.get("categoryName"))
    return ds


before = snap("记账前")
print("-" * 60)
s.payout(acc["id"], AMOUNT, cat["id"] if cat else 0,
         payTime=today.strftime("%Y-%m-%d 08:00"), memo="auto-sui自检-payout")
print("-" * 60)
if icat:
    s.income(acc["id"], AMOUNT, icat["id"],
             payTime=today.strftime("%Y-%m-%d 08:00"), memo="auto-sui自检-income")
    print("-" * 60)
if len(accounts) > 1:
    s.transfer(acc["id"], accounts[1]["id"], AMOUNT,
               payTime=today.strftime("%Y-%m-%d 08:00"), memo="auto-sui自检-transfer")
    print("-" * 60)
after = snap("记账后")
print("新增条数", len(after) - len(before))
