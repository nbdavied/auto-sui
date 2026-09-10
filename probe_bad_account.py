# -*- coding: utf-8 -*-
"""验证「把神象云的账户 id 拿去旧账本查流水 / 记账」会发生什么。

这是 Web 端上传账单后的实际路径:
  上传 -> conf.json 里的账户映射(suiid 是神象云 id) -> 旧账本对账 / 记账
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sui import Sui  # noqa: E402

BOGUS = "1183357936638279681"   # conf.json 里 622848****1211 映射的账户 id
conf = __import__("json").load(open("conf.json", encoding="utf-8"))
s = Sui({"username": conf["username"], "password": conf["password"]})
s.login()

print("== 用神象云 id 在旧账本里查流水 ==")
s.initTallyInfo("1505498391")
try:
    ds = s.accountDetail(BOGUS, "2026.01.01", "2026.09.10")
    print("返回", len(ds), "条")
except Exception as e:
    print("抛异常:", type(e).__name__, e)

print("== 用神象云 id 在旧账本里记账 ==")
# 在归档的旧账本里试,避免污染常用账本
s.initTallyInfo("1752598474")
accounts = getattr(s, "_Sui__accounts", []) or []
pays = getattr(s, "_Sui__payoutCategories", []) or []
cat = pays[0]["subCat"][0] if pays and pays[0].get("subCat") else None
print("真实分类", cat)
s.payout(BOGUS, "0.01", cat["id"] if cat else 0,
         payTime="2026-09-10 08:00", memo="auto-sui 错误账户自检")

print("== 查 0.01 是否落到任何账户 ==")
hit = 0
for acc in accounts:
    try:
        ds = s.accountDetail(acc["id"], "2026.09.10", "2026.09.10")
    except Exception as e:
        print("  ", acc["name"], "异常", e)
        continue
    for d in ds:
        if d.get("memo") == "auto-sui 错误账户自检":
            hit += 1
            print("   落到", acc["name"], d)
print("命中", hit, "条")
