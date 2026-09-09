# -*- coding: utf-8 -*-
"""神象云记账接口验证:在测试账本里记一笔支出/收入/转账。

所有账户 id / 分类 id 都从 conf.json 和账本实时获取,不在代码里硬编码个人数据。
"""
from configReader import readConfig
from shenxiang import ShenxiangClient


def pickCategory(categories):
    """取第一个可用分类(优先二级分类)。"""
    for cat in categories:
        if cat.get("subCat"):
            return cat["subCat"][0]
        return {"id": cat["id"], "name": cat["name"]}
    return None


if __name__ == "__main__":
    config = readConfig()
    client = ShenxiangClient(config)
    client.login()
    client.initTallyInfo()

    # 主账户取 conf.json 第一个;对手账户取账本里名为"现金"的账户,否则取第二个
    accounts = client.getAccounts()
    acc_bank = config["accounts"][0]["suiid"]
    acc_cash = next((a["id"] for a in accounts if a["name"] == "现金"), None)
    if acc_cash is None and len(accounts) > 1:
        acc_cash = accounts[1]["id"]

    cats = client.getCategories()
    cat_food = pickCategory(cats["payout"])
    cat_salary = pickCategory(cats["income"])

    print("主账户: %s" % acc_bank)
    print("对手账户: %s" % acc_cash)
    print("支出分类: %s / 收入分类: %s" % (cat_food, cat_salary))

    print("\n=== 1. 记一笔支出 0.01 元 ===")
    client.payout(acc_bank, "0.01", cat_food["id"], memo="自动记账测试-支出")

    print("\n=== 2. 记一笔收入 0.02 元 ===")
    client.income(acc_bank, "0.02", cat_salary["id"], memo="自动记账测试-收入")

    print("\n=== 3. 记一笔转账 0.03 元 (主账户->现金) ===")
    client.transfer(acc_bank, acc_cash, "0.03", memo="自动记账测试-转账")

    print("\n记账验证完成")
