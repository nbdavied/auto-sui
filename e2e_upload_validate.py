# -*- coding: utf-8 -*-
"""复现并验证修复:
  上传 622848****1211 的农行账单到旧账本
  -> conf.json 里的映射 suiid = 1183357936638279681 (神象云)
  -> 旧账本里这个 id 不存在
  -> 修复前:把这个 id 给前端 -> 对账查空 -> 已记账条目全显示未记账
  -> 修复后:服务端把 suiid 清空,让前端提示用户手选,避免 silent failure
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import openpyxl  # noqa: E402

from server import main as M  # noqa: E402
from server import store  # noqa: E402

conf = json.load(open("conf.json", encoding="utf-8"))


def buildBill():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet0"
    ws["A2"] = "账户：622848****1211 起始日期：20260101 截止日期：20260910"
    rows = [
        ("2026-08-07", "12:00:00", "-10000.00", "对手A", "111", "用途A", "备注A"),
        ("2026-09-09", "08:30:00", "-1.23", "对手B", "222", "用途B", "备注B"),
    ]
    for i, (d, t, amt, name, no, usage, memo) in enumerate(rows):
        ws.cell(row=4 + i, column=1, value=d)
        ws.cell(row=4 + i, column=2, value=t)
        ws.cell(row=4 + i, column=3, value=amt)
        ws.cell(row=4 + i, column=4, value=100.0)
        ws.cell(row=4 + i, column=5, value=name)
        ws.cell(row=4 + i, column=6, value=no)
        ws.cell(row=4 + i, column=7, value="")
        ws.cell(row=4 + i, column=8, value="")
        ws.cell(row=4 + i, column=10, value=usage)
        ws.cell(row=4 + i, column=11, value=memo)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


sid = M.sessions.create()
s = M.sessions.get(sid)
user = store.getOrCreateUser(conf["username"])
s["username"] = conf["username"]
s["password"] = conf["password"]
s["userId"] = user["id"]
s["legacyClient"] = M.legacy_sui_service.createClient(conf["username"], conf["password"])
s["provider"] = M.PROVIDER_LEGACY

print("== 切换到旧账本 ==")
print(M.selectBook(M.BookBody(sid=sid, bookId="1505498391",
                               provider=M.PROVIDER_LEGACY))["bookId"])

print("== 上传账单(应该把神象云 id 178... 识别为「不属于当前账本」并清空) ==")
from fastapi.testclient import TestClient
tc = TestClient(M.app)
resp = tc.post("/api/bills/upload",
               data={"sid": sid, "bankType": "abc"},
               files={"file": ("abc.xlsx", buildBill(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
print("status", resp.status_code)
body = resp.json()
print("bankno", body.get("bankno"), "suiid (期望为空):", repr(body.get("suiid")))
print("details 条数", body.get("count"))

print("== 不带 suiid 直接 reconcile 应该 400 ==")
resp = tc.post("/api/reconcile", json={"sid": sid, "suiid": ""})
print("status", resp.status_code, resp.json().get("detail", ""))

print("== 选错账户(神象云 id)对账应该 400 ==")
resp = tc.post("/api/reconcile", json={"sid": sid, "suiid": "1183357936638279681"})
print("status", resp.status_code, resp.json().get("detail", ""))

print("== 选对账户(旧 id)对账应该成功,匹配到 20260807 那条 ==")
resp = tc.post("/api/reconcile", json={"sid": sid, "suiid": "17330926177"})
print("status", resp.status_code)
items = resp.json().get("items", [])
for it in items:
    print(it["date"], it["amount"], it["transType"], "->", it["status"])

print("== 选对账户记账 ==")
resp = tc.post("/api/tally", json={
    "sid": sid, "suiid": "17330926177", "index": 1,
    "op": "payout", "catid": "51160931276", "memo": "auto-sui 修复验证"
})
print("status", resp.status_code, resp.json().get("message", ""))