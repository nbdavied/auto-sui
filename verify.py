# -*- coding: utf-8 -*-
"""神象云客户端只读验证脚本:登录 -> 账户/分类/成员 -> 流水查询。"""
import json
from shenxiang import ShenxiangClient


def readConfig():
    with open('conf.json', encoding='utf-8') as conf:
        return json.loads(conf.read())


if __name__ == "__main__":
    config = readConfig()
    client = ShenxiangClient(config)
    client.login()
    client.initTallyInfo()
    client.printAccounts()

    # 用第一个账户做流水查询验证(若无账户则跳过)
    accounts = client.getAccounts()
    if accounts:
        acc = accounts[0]
        print("\n查询账户流水:", acc["name"], acc["id"])
        details = client.accountDetail(acc["id"], "2026.09.01", "2026.09.10")
        print("流水条数:", len(details))
        for d in details[:10]:
            print(d)
    print("\n只读验证完成")
