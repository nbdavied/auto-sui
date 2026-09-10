# -*- coding: utf-8 -*-
"""诊断旧随手记(sui.py)的流水字段名与记账请求是否被服务端接受。

只读探测 + 可选的一笔记账测试(TALLY_TEST=1)。
"""
import json
import os
import sys
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sui import Sui  # noqa: E402

BOOK = os.environ.get("PROBE_BOOK", "1505498391")
BEGIN = os.environ.get("PROBE_BEGIN", "2026.01.01")

conf = json.load(open("conf.json", encoding="utf-8"))
s = Sui({"username": conf["username"], "password": conf["password"]})
s.login()
s.initTallyInfo(BOOK)

accounts = getattr(s, "_Sui__accounts", []) or []
today = datetime.date.today()
end = today.strftime("%Y.%m.%d")
begin = BEGIN.replace("-", ".")
print("账本", BOOK, "账户数", len(accounts), "查询区间", begin, "~", end)

hit = None
for acc in accounts:
    try:
        details = s.accountDetail(acc["id"], begin, end)
    except Exception as e:
        print("  账户", acc["id"], acc["name"], "查询异常", e)
        continue
    print("  账户", acc["id"], acc["name"], "->", len(details), "条")
    if details and hit is None:
        hit = (acc, details)

if hit:
    acc, details = hit
    print("=" * 70)
    print("样例流水来自账户", acc)
    for d in details[:3]:
        print("-" * 60)
        print(json.dumps(d, ensure_ascii=False, indent=1, default=str)[:3000])

if os.environ.get("TALLY_TEST") == "1":
    print("=" * 70)
    print("记账测试")
    pays = getattr(s, "_Sui__payoutCategories", []) or []
    incs = getattr(s, "_Sui__incomeCategories", []) or []
    acc = accounts[0]
    cat = pays[0]["subCat"][0] if pays and pays[0].get("subCat") else None
    print("account", acc, "category", cat)
    if cat:
        s.payout(acc["id"], "0.01", cat["id"], payTime="2026-09-10 08:00",
                 memo="auto-sui 记账自检")
        print("payout 已提交")
    if len(accounts) > 1 and incs and incs[0].get("subCat"):
        s.income(acc["id"], "0.01", incs[0]["subCat"][0]["id"],
                 payTime="2026-09-10 08:00", memo="auto-sui 记账自检")
        print("income 已提交")
    if len(accounts) > 1:
        s.transfer(acc["id"], accounts[1]["id"], "0.01",
                   payTime="2026-09-10 08:00", memo="auto-sui 记账自检")
        print("transfer 已提交")
