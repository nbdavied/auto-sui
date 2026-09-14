# -*- coding: utf-8 -*-
"""旧随手记 (sui.com) 服务封装 —— 与 sui_service.py 对称,但走 sui.py。

要点:
  - 每个会话持有一个已登录的 Sui 实例(内存),不落库
  - 账本清单不由这里提供:由 tally.feidee.net/mini_program/v1/books/list 动态获取,
    本模块只负责「拿到某个旧账本 id 后切换到它」
  - 所有数据访问都走 sui.py 原方法,不重复实现
  - 类别下钻(subCat)沿用 sui.py 原生结构,前端级联不需要特殊处理
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# sui.py 在项目根目录,与 shenxiang.py 平级
from sui import Sui  # noqa: E402

# 未显式指定账本时的回落值(sui.py 里的 DEFAULT_BOOK_ID 与之相同)
LEGACY_BOOK_ID = "1505498391"

# 错误页里通常夹带一个错误码,定位问题比「记账失败」有用得多
_ERROR_CODE_RE = re.compile(r"错误代码[:：]?\s*<[^>]*>([^<]+)<|错误代码[:：]?\s*([\w\-]+)")
_TRAN_ID_RE = re.compile(r"\d{6,}")


def _checkResult(r, opLabel):
    """把 sui.py 的 HTTP 响应当成「成功 / 失败」来判。

    sui.py 原来只 print 响应体,服务端报错(返回整张 HTML 错误页)时调用方
    完全无感知 —— 页面上显示"记账成功",账本里却什么都没有。这是当前最大的
    silent-failure 入口。

    成功响应形如 {id:{id:134923109120449},budget:0,price:0.01}(开头是 `{`,
    含 `id`)。失败响应是一整张带"出错啦"的 HTML 页(以 `<` 开头)。
    """
    if r is None:
        raise RuntimeError("%s: 没有收到服务端响应" % opLabel)
    if getattr(r, "status_code", 0) not in (200, 201):
        raise RuntimeError("%s: 服务端返回 HTTP %s" % (opLabel, getattr(r, "status_code", "?")))
    text = (getattr(r, "text", "") or "").strip()
    if not text or not text.startswith("{"):
        # 错误页里的错误码是最有用的线索 —— 截一小段出来
        code = ""
        m = _ERROR_CODE_RE.search(text)
        if m:
            code = m.group(1) or m.group(2) or ""
        hint = "错误代码 %s" % code if code else "服务端拒绝记账(很可能是账户 ID 或分类 ID 不存在)"
        raise RuntimeError("%s 被随手记拒绝: %s" % (opLabel, hint))
    match = _TRAN_ID_RE.search(text)
    return {"status_code": 200, "text": text[:200], "tranId": match.group(0) if match else ""}


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


def selectBook(client, bookId):
    """切换到指定的旧账本,并重新拉取该账本的账户 / 分类。

    旧体系「当前账本」存在服务端会话里,切换后必须重跑 initTallyInfo,
    否则拿回的还是上一个账本的数据 —— 账户和分类是对不上的。
    """
    if not client:
        raise RuntimeError("旧体系未登录")
    client.initTallyInfo(bookId or LEGACY_BOOK_ID)
    return {
        "accounts": buildAccountOptions(client),
        "categories": buildCategoryOptions(client),
    }


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


def accountExists(client, accountId):
    """对账 / 记账前先核对一下:这个 id 是不是当前账本里的账户。

    不然上传账单时若 conf.json 把神象云 id 错填过来,我们会拿一个「当前账本里
    不存在」的 account 去查流水,得到空列表 → 全部显示成未记账;再把它喂给
    payout,服务端会返回错误页 —— 而我们之前根本不知道。这就是用户看到的
    「已记账条目没有正确显示、记账操作也没有成功」。
    """
    if not accountId:
        return True   # 空 id 当作「未指定」,由前端兜底
    target = str(accountId)
    for a in _accounts(client):
        if str(a.get("id", "")) == target:
            return True
    return False


def payout(client, account, price, category, payTime=None, memo=""):
    """旧随手记支出记账。payTime / memo 与 shenxiang 同义。

    返回值是 `{status_code, text, tranId}` 的字典,失败抛 RuntimeError
    —— 失败信息包含服务端错误码,便于快速定位。
    """
    return _checkResult(
        client.payout(account, price, category, payTime=payTime, memo=memo),
        "支出记账")


def income(client, account, price, category, payTime=None, memo=""):
    """旧随手记收入记账。"""
    return _checkResult(
        client.income(account, price, category, payTime=payTime, memo=memo),
        "收入记账")


def transfer(client, out_account, in_account, price, payTime=None, memo=""):
    """旧随手记转账。

    注:sui.py:transfer 的参数顺序是 (out_account, in_account, price, ...)
    与神象云一致;不再额外调换。
    """
    return _checkResult(
        client.transfer(out_account, in_account, price, payTime=payTime, memo=memo),
        "转账记账")
