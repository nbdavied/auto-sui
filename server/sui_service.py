# -*- coding: utf-8 -*-
"""神象云服务封装: 把 shenxiang.py 包装成可服务化的形式。

要点:
  - 每个会话持有一个已登录的 ShenxiangClient 实例(内存),不落库
  - 复用现有 shenxiang.py,不做重复实现
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shenxiang import ShenxiangClient  # noqa: E402


def createClient(username, password, bookId=""):
    """创建客户端并完成登录(不初始化账本信息,选账本后再 init)。"""
    client = ShenxiangClient({
        "username": username,
        "password": password,
        "bookId": bookId or "",
    })
    client.login()
    return client


def createClientFromToken(token, bookId=""):
    """用浏览器里已有的 access_token 构造客户端,跳过密码登录。

    存在意义:服务端风控会给 OAuth 密码登录塞图形验证码(code 4099),
    但浏览器会话里那颗 token 依然有效。把它灌进来即可复用全部业务接口。
    """
    client = ShenxiangClient({
        "username": "",
        "password": "",
        "bookId": bookId or "",
    })
    client.setToken(token.strip())
    return client


def selectBook(client, bookId):
    """切换账本并拉取账户/分类/成员。"""
    client.setBookId(bookId)
    client.initTallyInfo()
    return {
        "accounts": client.getAccounts(),
        "categories": client.getCategories(),
    }


def buildAccountOptions(client):
    """账户列表 -> 前端下拉选项。"""
    return [{"id": a["id"], "name": a["name"],
             "group": a.get("group", ""), "type": a.get("type", "")}
            for a in client.getAccounts()]


def buildCategoryOptions(client):
    """分类 -> 前端级联选项 {income: [...], payout: [...]}。"""
    def conv(cats):
        return [{"id": c["id"], "name": c["name"],
                 "children": [{"id": s["id"], "name": s["name"]} for s in c.get("subCat", [])]}
                for c in cats]
    cats = client.getCategories()
    return {"income": conv(cats["income"]), "payout": conv(cats["payout"])}
