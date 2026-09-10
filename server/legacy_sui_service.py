# -*- coding: utf-8 -*-
"""旧随手记 (sui.com) 服务封装 —— 与 sui_service.py 对称,但走 sui.py。

要点:
  - 每个会话持有一个已登录的 Sui 实例(内存),不落库
  - 旧体系只有一本书(bookId 写死在 sui.py 内),不需要 getBooks 多分页
  - 所有数据访问都走 sui.py 原方法,不重复实现
  - 类别下钻(subCat)沿用 sui.py 原生结构,前端级联不需要特殊处理
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# sui.py 在项目根目录,与 shenxiang.py 平级
from sui import Sui  # noqa: E402

# 旧随手记只有一个账本,这个 id 在 sui.py:__authRedirect / initTallyInfo 里写死
LEGACY_BOOK_ID = "1505498391"
LEGACY_BOOK_NAME = "旧随手记账本"
LEGACY_PROVIDER = "legacy"


def createClient(username, password):
    """登录旧随手记并完成初始数据加载。

    sui.py:initTallyInfo() 会拉取账户与分类,这一步不可省略 —— 否则后续
    payout / income 都拿不到 account id 与 category id。
    """
    cfg = {"username": username, "password": password}
    client = Sui(cfg)
    client.login()
    client.initTallyInfo()
    return client


def listBooks():
    """旧体系只有一个账本;返回 shape 与神象云保持一致,便于前端按 provider 路由。"""
    return [{
        "id": LEGACY_BOOK_ID,
        "name": LEGACY_BOOK_NAME,
        "provider": LEGACY_PROVIDER,
    }]


def selectBook(_client, _bookId):
    """旧体系无需切换:login 阶段已经把当前账本的账户/分类加载好了。
    保留这个函数让 main.py / sui_service.py 接口对齐。
    """
    return {}


def _accounts(client):
    """取出旧体系的账户列表。

    sui.py 没有 getAccounts/__accounts public 暴露,实例属性是
    name-mangled 的 self.__accounts(以 _Sui__accounts 形式存在)。
    读 mangle 后的字段是 Python 社区约定俗成的做法,不动 sui.py 本体。
    """
    return getattr(client, "_Sui__accounts", None) or []


def _categories(client, attr):
    raw = getattr(client, attr, None)
    # __incomeCategories / __payoutCategories 是列表;若是 None 表示未初始化
    return raw if isinstance(raw, list) else []


def buildAccountOptions(client):
    """账户列表 -> 前端下拉选项。shape 与神象云一致。"""
    out = []
    for a in _accounts(client):
        # name-mangled 字典,字段就只有 id / name
        out.append({"id": str(a.get("id", "")), "name": a.get("name", "") or "",
                    "group": "", "type": ""})
    return out


def buildCategoryOptions(client):
    """分类 -> 前端级联选项 {income, payout}。shape 与神象云一致。

    sui.py 的类别嵌套是 [{id, name, subCat:[{id, name}, ...]}, ...];
    把它拍平成前端级联需要的 [{id, name, children: [...]}] 即可。
    """

    def conv(cats):
        return [{"id": c["id"], "name": c["name"],
                 "children": [{"id": s["id"], "name": s["name"]}
                              for s in c.get("subCat", [])]}
                for c in cats]

    return {"income": conv(_categories(client, "_Sui__incomeCategories")),
            "payout": conv(_categories(client, "_Sui__payoutCategories"))}


def payout(client, account, price, category, payTime=None, memo=""):
    """旧随手记支出记账。payTime / memo 与 shenxiang 同义。"""
    # sui.payout 内部会在 payTime is None 时用本地时间兜底
    client.payout(account, price, category, payTime=payTime, memo=memo)


def income(client, account, price, category, payTime=None, memo=""):
    """旧随手记收入记账。"""
    client.income(account, price, category, payTime=payTime, memo=memo)


def transfer(client, out_account, in_account, price, payTime=None, memo=""):
    """旧随手记转账。

    注:sui.py:transfer 的参数顺序是 (out_account, in_account, price, ...)
    与神象云一致;不再额外调换。
    """
    client.transfer(out_account, in_account, price, payTime=payTime, memo=memo)
