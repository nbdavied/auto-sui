# -*- coding: utf-8 -*-
"""列出指定账本下的所有账户(用于配置 bankno -> 神象云账户id 映射)。

用法:
    python list_accounts.py [账本id]

不传账本id时,使用 conf.json 里的 bookId。
输出: 序号 / 账户名 / 账户id / 类型 / 分组 / 余额
"""
import sys
import json
from configReader import readConfig
from shenxiang import ShenxiangClient


def main():
    config = readConfig()
    if len(sys.argv) > 1:
        config["bookId"] = sys.argv[1]

    client = ShenxiangClient(config)
    client.login()
    client.initTallyInfo()

    accounts = client.getAccounts()
    print()
    print("=" * 70)
    print("账本 id: %s" % config["bookId"])
    print("账户总数: %d" % len(accounts))
    print("=" * 70)
    print("序号 | 账户名 | 账户id | 类型 | 分组 | 余额")
    print("-" * 70)
    for i, a in enumerate(accounts):
        print("%2d | %s | %s | %s | %s | %s" % (
            i, a.get("name", ""), a.get("id", ""),
            a.get("type", ""), a.get("group", ""), a.get("balance", "")))
    print("=" * 70)
    print()
    print("请告诉我每个账户对应的序号(或账户id),我来更新 conf.json 的 suiid。")

    # 顺便输出 JSON 便于脚本处理
    with open("accounts.json", "w", encoding="utf-8") as f:
        json.dump(accounts, f, ensure_ascii=False, indent=2)
    print("账户清单已写入 accounts.json")


if __name__ == "__main__":
    main()
