# -*- coding: utf-8 -*-
"""Web API 冒烟测试: 登录 -> 选账本 -> 上传账单 -> 对账。

只打印统计信息,不打印流水明细,避免个人信息进入日志。
如需记账验证,加 --tally 参数(会在测试账本记一笔)。
"""
import sys
import json
import requests

BASE = "http://127.0.0.1:8000"


def main():
    conf = json.load(open("conf.json", encoding="utf-8"))
    billPath = sys.argv[1] if len(sys.argv) > 1 else "bankdetails/abc_detail20260909.xlsx"

    r = requests.get(BASE + "/api/health", timeout=10).json()
    print("1. health:", r)

    r = requests.post(BASE + "/api/login", timeout=30,
                      json={"username": conf["username"],
                            "password": conf["password"]}).json()
    sid = r["sid"]
    print("2. login: 账本 %d 个 -> %s" % (len(r["books"]),
                                       [b["name"] for b in r["books"]]))

    bookId = "1183356777640235009"   # 测试账本
    r = requests.post(BASE + "/api/book", timeout=30,
                      json={"sid": sid, "bookId": bookId}).json()
    print("3. book: 账户 %d 个, 支出分类 %d 个" % (
        len(r["accounts"]), len(r["categories"]["payout"])))

    with open(billPath, "rb") as f:
        r = requests.post(BASE + "/api/bills/upload", timeout=60,
                          data={"sid": sid},
                          files={"file": (billPath.split("/")[-1], f)}).json()
    print("4. upload: 卡号 %s, 建议账户 %s, 明细 %d 条" % (
        r["bankno"], r["suiid"], r["count"]))

    suiid = r["suiid"] or "1183357936638279681"
    r = requests.post(BASE + "/api/reconcile", timeout=60,
                      json={"sid": sid, "suiid": suiid}).json()
    if "items" not in r:
        print("5. reconcile 失败:", json.dumps(r, ensure_ascii=False)[:500])
        return
    items = r["items"]
    stat = {}
    for it in items:
        stat[it["status"]] = stat.get(it["status"], 0) + 1
    print("5. reconcile: 共 %d 条 -> %s" % (len(items), stat))

    if "--tally" in sys.argv:
        idx = next((i for i, it in enumerate(items) if it["status"] != "matched"), None)
        if idx is None:
            print("6. tally: 没有未入账条目,跳过")
            return
        cat = requests.get(BASE + "/api/categories",
                           params={"sid": sid}, timeout=30).json()
        catId = cat["categories"]["payout"][0]["children"][0]["id"]
        r = requests.post(BASE + "/api/tally", timeout=30, json={
            "sid": sid, "suiid": suiid, "index": idx,
            "op": "payout", "catid": catId, "memo": "自动记账测试-web"}).json()
        print("6. tally:", r)

    print("\n冒烟测试通过")


if __name__ == "__main__":
    main()
