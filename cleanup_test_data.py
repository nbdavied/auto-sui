# -*- coding: utf-8 -*-
"""清理神象云测试账本里的自动记账测试流水。

用法:
    python cleanup_test_data.py              # 只列出,不删除
    python cleanup_test_data.py --delete     # 确认后删除

默认只匹配备注含 "自动记账测试" 的流水,不会碰其他数据。
"""
import sys
from configReader import readConfig
from shenxiang import ShenxiangClient

MARK = "自动记账测试"
BEGIN, END = "2026.01.01", "2026.12.31"


def main():
    doDelete = "--delete" in sys.argv
    config = readConfig()
    client = ShenxiangClient(config)
    client.login()
    client.initTallyInfo()

    print("扫描账本 %s (%s ~ %s) 中备注含「%s」的流水..." % (
        config.get("bookId"), BEGIN, END, MARK))
    items = client.queryAll(BEGIN, END)
    print("账本流水总数: %d" % len(items))

    targets = []
    for it in items:
        remark = (it.get("remark") or "")
        if MARK not in remark:
            continue
        amount = it.get("amount") or it.get("from_amount") or ""
        targets.append({
            "id": str(it.get("id", "")),
            "remark": remark,
            "type": it.get("business_type", ""),
            "amount": amount,
        })

    if not targets:
        print("未找到测试数据,无需清理。")
        return

    print("\n待清理 %d 笔:" % len(targets))
    for t in targets:
        print("  %s | %s | %s | %s" % (t["id"], t["type"], t["amount"], t["remark"]))

    if not doDelete:
        print("\n这是预演模式。确认无误后执行: python cleanup_test_data.py --delete")
        return

    print("\n开始删除...")
    failed = []
    r = client.deleteTransactions([t["id"] for t in targets])
    if r.get("ok"):
        print("  批量删除成功 (%s %s -> %s)" % (r["method"], r["path"], r["status"]))
        print("  响应:", r.get("text", ""))
    else:
        print("  批量删除失败,改为逐条尝试...")
        for t in targets:
            one = client.deleteTransaction(t["id"])
            if one.get("ok"):
                print("  [已删除] %s (%s)" % (t["id"], t["remark"]))
            else:
                failed.append(t)
                print("  [失败]   %s -> %s %s" % (t["id"], one.get("status"), one.get("text", "")))

    print("\n重新校验剩余测试数据...")
    left = [it for it in client.queryAll(BEGIN, END)
            if MARK in (it.get("remark") or "")]
    print("剩余 %d 笔" % len(left))
    if left:
        print("删除接口可能不可用,请在网页端手动删除以上流水。")


if __name__ == "__main__":
    main()
