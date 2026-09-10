# -*- coding: utf-8 -*-
"""找出旧账本里近期有流水的账户,打印样例流水(供构造对账测试用例)。"""
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sui import Sui  # noqa: E402

BOOK = os.environ.get("PROBE_BOOK", "1505498391")
DAYS = int(os.environ.get("PROBE_DAYS", "120"))

conf = json.load(open("conf.json", encoding="utf-8"))
s = Sui({"username": conf["username"], "password": conf["password"]})
s.login()
s.initTallyInfo(BOOK)
accounts = getattr(s, "_Sui__accounts", []) or []

today = datetime.date.today()
end = today.strftime("%Y.%m.%d")
begin = (today - datetime.timedelta(days=DAYS)).strftime("%Y.%m.%d")
print("区间", begin, "~", end)
for acc in accounts:
    try:
        ds = s.accountDetail(acc["id"], begin, end)
    except Exception as e:
        print("ERR", acc["id"], acc["name"], e)
        continue
    if not ds:
        continue
    print("=" * 60)
    print("账户", acc["id"], acc["name"], len(ds), "条")
    for d in ds[:6]:
        print("   %s type=%s amt=%s cat=%s buyer=%s(%s) seller=%s(%s) memo=%s" % (
            d.get("sdate"), d.get("tranType"), d.get("itemAmount"),
            d.get("categoryName"), d.get("buyerAcount"), d.get("buyerAcountId"),
            d.get("sellerAcount"), d.get("sellerAcountId"), d.get("memo")))
