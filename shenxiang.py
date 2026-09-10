# -*- coding: utf-8 -*-
"""
神象云账本客户端
================

逆向自神象云账本网页版 (www.feidee.com/cloud/) 前端,接口契约如下:

登录 (OAuth2 password):
  GET https://auth.feidee.net/v2/oauth2/authorize
    ?grant_type=password_web&encode_version=V4&scope=user
     &username=<email>&password=<sha1(明文)>&vcid=&vid=
  请求头:
    App-Id: cab-web
    Type: MD5-H5
    Minor-Version: 2
    Client-Key: 520BFC1EA31D45678A9B865668A47F40
    Nonce-Str: <16位随机数字>
    Timestamp: <毫秒>
    Sign: md5(Client-Key + Nonce-Str + Timestamp)     # 密钥为空字符串
  响应: {access_token, refresh_token, token_type: "Bearer"}

业务接口 (yun.feidee.net 的 cab-* 系列):
  请求头:
    Authorization: Bearer <access_token>
    Trading-Entity: <账本id>
    Device: <设备JSON>
    Client-Key: PiVEoJM9OHFS8xFlnD3CuSrJgRgyVLwS
    Nonce-Str / Timestamp
    Sign: md5(Client-Key + Nonce-Str + Timestamp + "pQhGxs0I84zQgeU8")

  记账:
    POST /cab-accounting-ws/v2/account-book/transaction/expense
    POST /cab-accounting-ws/v2/account-book/transaction/income
    POST /cab-accounting-ws/v2/account-book/transaction/transfer
  账户/分类:
    GET  /cab-config-ws/v2/account-book/accounts?scene=Accounting&operation_codes=C
    GET  /cab-config-ws/v2/account-book/categories?trade_type=&operation_codes=C
  流水:
    POST /cab-query-ws/v2/statistics/transactions
"""
import requests
import json
import time
import hashlib
import random
import uuid
import re
from datetime import datetime, timezone, timedelta

# 神象云返回的 transaction_time 是 Unix 毫秒,业务侧始终按北京时间理解。
# 不强制 datetime(..., tzinfo=...)=UTC 是因为服务器可能跑在任何时区。
# 注意:这条常量只用于「账本流水日期」语义 —— 如果未来要支持海外账本,再扩展。
_BEIJING_TZ = timezone(timedelta(hours=8))

# 登录签名用的 Client-Key (生产环境)
AUTH_CLIENT_KEY = "520BFC1EA31D45678A9B865668A47F40"
# 业务接口签名用的 Client-Key 与密钥 (前端硬编码)
BIZ_CLIENT_KEY = "PiVEoJM9OHFS8xFlnD3CuSrJgRgyVLwS"
BIZ_SECRET = "pQhGxs0I84zQgeU8"

AUTH_BASE = "https://auth.feidee.net"
BIZ_BASE = "https://yun.feidee.net"

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0")


class ShenxiangClient:
    """神象云账本客户端,对外接口与老 sui.Sui 保持兼容,方便 run.py 复用。"""

    def __init__(self, config):
        self.__config = config
        self.__session = requests.session()
        self.__token = ""          # access_token
        self.__tokenType = "Bearer"
        self.__bookId = config.get("bookId", "")
        self.__device = self.__buildDevice()

        # 缓存
        self.__accounts = []        # [{id, name, type, balance, group}]
        self.__incomeCategories = []  # [{id, name, subCat:[{id,name}]}]
        self.__payoutCategories = []
        self.__members = []         # [{id, name}]

    # ------------------------------------------------------------------ #
    # 工具
    # ------------------------------------------------------------------ #
    @staticmethod
    def __md5(s):
        return hashlib.md5(s.encode("utf-8")).hexdigest()

    @staticmethod
    def __genNonce():
        return str(random.randint(0, 10 ** 16)).zfill(16)

    @staticmethod
    def __buildDevice():
        device_id = "fed-" + str(uuid.uuid4())
        return json.dumps({
            "model": "win64;",
            "platform": "Win32",
            "os_version": "",
            "device_id": device_id,
            "product_name": "cab-web",
            "product_version": "139.0.0.0",
            "locale": "zh-CN",
            "time_zone": "Asia/Shanghai",
        }, ensure_ascii=False)

    def __signHeaders(self, clientKey, secret):
        nonce = self.__genNonce()
        ts = str(int(time.time() * 1000))
        sign = self.__md5(clientKey + nonce + ts + secret)
        return {
            "Client-Key": clientKey,
            "Nonce-Str": nonce,
            "Timestamp": ts,
            "Sign": sign,
        }

    def __bizHeaders(self):
        headers = self.__signHeaders(BIZ_CLIENT_KEY, BIZ_SECRET)
        headers.update({
            "Authorization": "%s %s" % (self.__tokenType, self.__token),
            "Trading-Entity": self.__bookId,
            "Device": self.__device,
            "Content-Type": "application/json",
            "Origin": "https://www.feidee.com",
            "Referer": "https://www.feidee.com/",
            "User-Agent": USER_AGENT,
        })
        return headers

    def __get(self, path, params=None):
        url = BIZ_BASE + path
        r = self.__session.get(url, params=params, headers=self.__bizHeaders(), timeout=15)
        return r

    def __post(self, path, body=None):
        url = BIZ_BASE + path
        data = json.dumps(body, ensure_ascii=False) if body is not None else None
        r = self.__session.post(url, data=data, headers=self.__bizHeaders(), timeout=15)
        return r

    # ------------------------------------------------------------------ #
    # 登录
    # ------------------------------------------------------------------ #
    def login(self):
        print("正在登录神象云账本")
        username = self.__config["username"]
        password = self.__config["password"]
        pwdHash = hashlib.sha1(password.encode("utf-8")).hexdigest()

        headers = self.__signHeaders(AUTH_CLIENT_KEY, "")
        headers.update({
            "App-Id": "cab-web",
            "Type": "MD5-H5",
            "Minor-Version": "2",
            "Device": self.__device,
            "Origin": "https://www.feidee.com",
            "Referer": "https://www.feidee.com/",
            "Accept": "application/json, text/plain, */*",
            "User-Agent": USER_AGENT,
        })
        params = {
            "grant_type": "password_web",
            "encode_version": "V4",
            "scope": "user",
            "username": username,
            "password": pwdHash,
            "vcid": "",
            "vid": "",
        }
        r = self.__session.get(AUTH_BASE + "/v2/oauth2/authorize",
                               params=params, headers=headers, timeout=15)
        try:
            data = r.json()
        except Exception:
            print("登录响应异常:", r.status_code, r.text[:500])
            raise
        if "access_token" not in data:
            print("登录失败:", data)
            raise Exception("登录失败: %s" % data.get("message", data))
        self.__token = data["access_token"]
        self.__tokenType = data.get("token_type", "Bearer")
        self.__refreshToken = data.get("refresh_token", "")
        print("登录成功")
        return data

    # ------------------------------------------------------------------ #
    # 初始化账本信息 (账户 / 分类 / 成员)
    # ------------------------------------------------------------------ #
    def initTallyInfo(self):
        print("初始化神象云账本信息 (账本id=%s)" % self.__bookId)
        self.__initAccounts()
        self.__initCategories()
        self.__initMembers()

    def setBookId(self, bookId):
        """切换当前操作的账本(登录后选账本时用)。"""
        self.__bookId = str(bookId)

    def getBookId(self):
        return self.__bookId

    def getBooks(self):
        """返回当前账号的账本列表 [{id, name}]。

        实测可用接口: GET /cab-index-ws/v3/book-group/cloud -> {cloud_book_list: [...]}
        """
        paths = [
            "/cab-index-ws/v3/book-group/cloud",
            "/cab-config-ws/v2/account-books",
        ]
        for path in paths:
            try:
                r = self.__get(path)
                if r.status_code != 200:
                    continue
                data = r.json()
                arr = None
                for key in ("cloud_book_list", "book_list", "data"):
                    v = data.get(key)
                    if isinstance(v, list) and v:
                        arr = v
                        break
                    if isinstance(v, dict):
                        arr = v.get("books") or v.get("list") or []
                        if arr:
                            break
                if not arr:
                    continue
                books = []
                for b in arr:
                    bid = b.get("id") or b.get("book_id")
                    name = b.get("name") or b.get("book_name")
                    if bid:
                        books.append({"id": str(bid), "name": name or str(bid)})
                if books:
                    return books
            except Exception:
                continue
        return []

    def __initAccounts(self):
        r = self.__get("/cab-config-ws/v2/account-book/accounts",
                       params={"scene": "Accounting", "operation_codes": "C"})
        data = r.json()
        self.__accounts = []
        for group in data.get("data", []):
            groupName = group.get("name", "")
            for acc in group.get("accounts", []):
                self.__accounts.append({
                    "id": str(acc.get("id", "")),
                    "name": acc.get("name", ""),
                    "type": acc.get("type", ""),
                    "balance": acc.get("balance", ""),
                    "group": groupName,
                })
        print("账户列表:", [(a["id"], a["name"]) for a in self.__accounts])

    def __initCategories(self):
        r = self.__get("/cab-config-ws/v2/account-book/categories",
                       params={"trade_type": "", "operation_codes": "C"})
        data = r.json()
        self.__incomeCategories = []
        self.__payoutCategories = []
        for cat in data.get("data", []):
            ctype = cat.get("type", "")
            node = {
                "id": str(cat.get("id", "")),
                "name": cat.get("name", ""),
                "subCat": [{"id": str(s.get("id", "")), "name": s.get("name", "")}
                           for s in cat.get("sub_categories", [])],
            }
            if ctype == "Income":
                self.__incomeCategories.append(node)
            elif ctype == "Expense":
                self.__payoutCategories.append(node)
        print("收入分类:", [(c["id"], c["name"]) for c in self.__incomeCategories])
        print("支出分类:", [(c["id"], c["name"]) for c in self.__payoutCategories])

    def __initMembers(self):
        try:
            r = self.__get("/cab-config-ws/v2/account-book/members")
            data = r.json()
            self.__members = [{"id": str(m.get("id", "")), "name": m.get("name", "")}
                              for m in data.get("data", [])]
        except Exception:
            self.__members = []
        print("成员列表:", self.__members)

    # ------------------------------------------------------------------ #
    # 记账
    # ------------------------------------------------------------------ #
    def __defaultMember(self):
        if self.__members:
            return {"id": self.__members[0]["id"]}
        return None

    # 银行账单部分条目只有日期没有时间,统一按 08:00:00 记账(不要用当前时间,否则日期会漂到今天)
    DEFAULT_HOUR = 8
    DEFAULT_MINUTE = 0

    @classmethod
    def __todayDefaultMs(cls):
        """今天 08:00:00 的毫秒时间戳(完全拿不到日期时的兜底)。"""
        dt = datetime.now().replace(hour=cls.DEFAULT_HOUR, minute=cls.DEFAULT_MINUTE,
                                    second=0, microsecond=0)
        return int(dt.timestamp() * 1000)

    @classmethod
    def __dateDefaultMs(cls, year, month, day):
        """指定日期的 08:00:00 毫秒时间戳。"""
        dt = datetime(int(year), int(month), int(day),
                      cls.DEFAULT_HOUR, cls.DEFAULT_MINUTE, 0)
        return int(dt.timestamp() * 1000)

    def __payTimeToMs(self, payTime):
        """把 payTime 转成毫秒时间戳。

        支持: None / 空串 / 时间戳 / "YYYY-MM-DD HH:MM:SS" / "YYYY-MM-DD HH:MM" /
              "YYYY-MM-DD" / "YYYYMMDDHHMMSS" / "YYYYMMDD" / 带空时间的 "YYYY-MM-DD :"。
        只有日期没有时间时,时间统一补 08:00:00。
        """
        if isinstance(payTime, (int, float)):
            return int(payTime)
        if payTime is None:
            return self.__todayDefaultMs()

        s = str(payTime).strip()
        if not s:
            return self.__todayDefaultMs()

        m = re.match(
            r"^(\d{4})[-/.\s]*(\d{1,2})[-/.\s]*(\d{1,2})"
            r"(?:[-/.\sT]*(\d{1,2}):?(\d{1,2})?:?(\d{1,2})?)?", s)
        if not m:
            return self.__todayDefaultMs()
        y, mo, d = m.group(1), m.group(2), m.group(3)
        hh, mm, ss = m.group(4), m.group(5), m.group(6)
        try:
            if hh is None:  # 只有日期,时间取默认值
                return self.__dateDefaultMs(y, mo, d)
            dt = datetime(int(y), int(mo), int(d),
                          int(hh), int(mm or 0), int(ss or 0))
            return int(dt.timestamp() * 1000)
        except ValueError:
            return self.__dateDefaultMs(y, mo, d)

    def __optionalDims(self):
        """返回 member/merchant/project 可选维度字典。

        若 config 里配置了默认 id 则带上;否则 member 默认取账本主人,
        merchant/project 不传(部分账本模板无此维度)。"""
        dims = {}
        m = self.__config.get("defaultMember")
        if m:
            dims["member"] = {"id": str(m)}
        elif self.__members:
            dims["member"] = self.__defaultMember()
        if self.__config.get("defaultMerchant"):
            dims["merchant"] = {"id": str(self.__config["defaultMerchant"])}
        if self.__config.get("defaultProject"):
            dims["project"] = {"id": str(self.__config["defaultProject"])}
        return dims

    def payout(self, account, price, category, payTime=None, memo=""):
        body = {
            "business_type": "Expense",
            "account": {"id": str(account)},
            "category": {"id": str(category)},
            "amount": str(price),
            "remark": memo or "",
            "transaction_time": self.__payTimeToMs(payTime),
        }
        body.update(self.__optionalDims())
        r = self.__post("/cab-accounting-ws/v2/account-book/transaction/expense", body)
        print("支出记账结果:", r.status_code, r.text[:300])
        return r

    def income(self, account, price, category, payTime=None, memo=""):
        body = {
            "business_type": "Income",
            "account": {"id": str(account)},
            "category": {"id": str(category)},
            "amount": str(price),
            "remark": memo or "",
            "transaction_time": self.__payTimeToMs(payTime),
        }
        body.update(self.__optionalDims())
        r = self.__post("/cab-accounting-ws/v2/account-book/transaction/income", body)
        print("收入记账结果:", r.status_code, r.text[:300])
        return r

    def transfer(self, out_account, in_account, price, payTime=None, memo=""):
        body = {
            "business_type": "Transfer",
            "from_account": {"id": str(out_account)},
            "to_account": {"id": str(in_account)},
            "from_amount": str(price),
            "to_amount": str(price),
            "remark": memo or "",
            "transaction_time": self.__payTimeToMs(payTime),
        }
        body.update(self.__optionalDims())
        r = self.__post("/cab-accounting-ws/v2/account-book/transaction/transfer", body)
        print("转账记账结果:", r.status_code, r.text[:300])
        return r

    # ------------------------------------------------------------------ #
    # 流水查询 (对账去重用)
    # ------------------------------------------------------------------ #
    @staticmethod
    def __dateToMs(dateStr, endOfDay=False):
        """把 'YYYY.MM.DD' / 'YYYYMMDD' 转成毫秒时间戳。"""
        s = str(dateStr).replace(".", "").replace("-", "").replace("/", "")
        if len(s) != 8:
            raise ValueError("日期格式错误: %s" % dateStr)
        if endOfDay:
            dt = datetime.strptime(s, "%Y%m%d").replace(hour=23, minute=59, second=59)
        else:
            dt = datetime.strptime(s, "%Y%m%d")
        return int(dt.timestamp() * 1000)

    def queryAll(self, beginDate, endDate):
        """查询整个账本(不限账户)在日期区间内的原始流水,含 remark/business_type 等字段。"""
        startMs = self.__dateToMs(beginDate)
        endMs = self.__dateToMs(endDate, endOfDay=True)
        items = []
        pageOffset = 0
        pageSize = 200
        while True:
            body = {
                "query": {"start_time": startMs, "end_time": endMs},
                "sort": {"order_by": "DESC", "sort_by": "ACCOUNT_TIME"},
                "page": {"page_offset": pageOffset, "page_size": pageSize},
                "extend": {"scene": "Account"},
            }
            r = self.__post("/cab-query-ws/v2/statistics/transactions", body)
            data = r.json()
            items.extend(data.get("data", []))
            paging = data.get("paging", {})
            if not paging.get("has_more"):
                break
            pageOffset += pageSize
        return items

    def rawRequest(self, method, path, body=None, extraHeaders=None):
        """发一个带签名的业务请求,返回 Response(用于探测未封装的接口,如删除)。"""
        url = BIZ_BASE + path
        headers = self.__bizHeaders()
        if extraHeaders:
            headers.update(extraHeaders)
        if body is None:
            return self.__session.request(method, url, headers=headers, timeout=15)
        return self.__session.request(method, url,
                                      data=json.dumps(body, ensure_ascii=False),
                                      headers=headers, timeout=15)

    def deleteTransactions(self, tranIds):
        """批量删除流水。

        前端对交易用的是 POST + X-HTTP-Method-Override 的写法(编辑为 PATCH),
        删除推测同理,故这里按多种形式依次尝试。
        """
        ids = [str(i) for i in tranIds]
        candidates = [
            ("POST", "/cab-accounting-ws/v3/account-book/transactions",
             {"ids": ids}, {"X-HTTP-Method-Override": "DELETE"}),
            ("DELETE", "/cab-accounting-ws/v3/account-book/transactions",
             {"ids": ids}, None),
            ("POST", "/cab-accounting-ws/v2/account-book/transaction/%s" % ids[0],
             None, {"X-HTTP-Method-Override": "DELETE"}),
            ("DELETE", "/cab-accounting-ws/v2/account-book/transaction/%s" % ids[0],
             None, None),
        ]
        last = None
        for method, path, body, extra in candidates:
            r = self.rawRequest(method, path, body, extra)
            last = r
            if r.status_code in (200, 201, 204):
                return {"ok": True, "method": method, "path": path,
                        "status": r.status_code, "text": r.text[:200]}
        return {"ok": False, "status": getattr(last, "status_code", None),
                "text": (last.text[:200] if last is not None else "")}

    def deleteTransaction(self, tranId):
        """删除单笔流水。"""
        return self.deleteTransactions([tranId])

    def accountDetail(self, accountId, beginDate, endDate):
        """查询某账户在日期区间内的流水,返回与老 sui 兼容的结构。

        每条: {sdate, itemAmount, tranType, tranId, sellerAcountId, buyerAcountId}
          tranType: 1=支出, 2=转账, 5=收入
        """
        startMs = self.__dateToMs(beginDate)
        endMs = self.__dateToMs(endDate, endOfDay=True)
        details = []
        pageOffset = 0
        pageSize = 200
        while True:
            body = {
                "query": {
                    "account_ids": [str(accountId)],
                    "start_time": startMs,
                    "end_time": endMs,
                },
                "sort": {"order_by": "DESC", "sort_by": "ACCOUNT_TIME"},
                "page": {"page_offset": pageOffset, "page_size": pageSize},
                "extend": {"scene": "Account"},
            }
            r = self.__post("/cab-query-ws/v2/statistics/transactions", body)
            data = r.json()
            for item in data.get("data", []):
                d = self.__mapDetail(item)
                if d:
                    details.append(d)
            paging = data.get("paging", {})
            if not paging.get("has_more"):
                break
            pageOffset += pageSize
        return details

    @staticmethod
    def __mapDetail(item):
        """把神象云流水中转成老 sui 对账兼容结构,顺便留住展示所需字段。

        兼容字段(sdate/tranId/sellerAcountId/buyerAcountId/itemAmount/tranType)
        决定对账匹配,不能动。新增字段全部带 detail 前缀,避免与老结构冲突。
        """
        bt = item.get("business_type")
        # 余额调整流水不参与对账
        if bt == "Balance_Changed":
            return None
        ts = item.get("transaction_time")
        if ts:
            try:
                tsInt = int(ts)
                # 毫秒或秒 → 一律先归一化成秒
                seconds = tsInt / 1000 if tsInt > 10 ** 12 else tsInt
                # 服务器所在的时区不一定是北京,但账本业务是北京时间,
                # 所以 sdate 与 detailTransactionTime 都按 Asia/Shanghai 算。
                d = datetime.fromtimestamp(seconds, tz=_BEIJING_TZ)
                sdate = d.strftime("%Y%m%d")
            except Exception:
                sdate = ""
        else:
            sdate = ""

        detail = {
            "sdate": sdate,
            "tranId": str(item.get("id", "")),
            "sellerAcountId": "",
            "buyerAcountId": "",
            "itemAmount": 0.0,
            "tranType": 0,
            # 展示用字段。命名都加 detail 前缀,避免未来冲突。
            "detailRemark": item.get("remark", "") or "",
            "detailTransactionTime": ts,                  # 原值,毫秒或秒
            "detailCategoryId": "",
            "detailCategoryName": "",
            "detailAccountId": "",
            "detailAccountName": "",
            "detailFromAccountId": "",
            "detailFromAccountName": "",
            "detailToAccountId": "",
            "detailToAccountName": "",
            "detailMemberId": (item.get("member") or {}).get("id", "") if item.get("member") else "",
            "detailMemberName": (item.get("member") or {}).get("name", "") if item.get("member") else "",
            "detailMerchant": (item.get("merchant") or {}).get("name", "") if item.get("merchant") else "",
        }
        cat = item.get("category") or {}
        if isinstance(cat, dict):
            detail["detailCategoryId"] = str(cat.get("id", ""))
            detail["detailCategoryName"] = cat.get("name", "") or ""
        if bt == "Expense":
            detail["tranType"] = 1
            detail["itemAmount"] = float(item.get("amount") or 0)
            # 支出:account=本账户(从这个账户出钱)
            acc = item.get("account") or {}
            detail["detailAccountId"] = str(acc.get("id", ""))
            detail["detailAccountName"] = acc.get("name", "") or ""
        elif bt == "Income":
            detail["tranType"] = 5
            detail["itemAmount"] = float(item.get("amount") or 0)
            acc = item.get("account") or {}
            detail["detailAccountId"] = str(acc.get("id", ""))
            detail["detailAccountName"] = acc.get("name", "") or ""
        elif bt == "Transfer":
            detail["tranType"] = 2
            detail["itemAmount"] = float(item.get("from_amount") or item.get("to_amount") or 0)
            fa = item.get("from_account") or {}
            ta = item.get("to_account") or {}
            detail["detailFromAccountId"] = str(fa.get("id", ""))
            detail["detailFromAccountName"] = fa.get("name", "") or ""
            detail["detailToAccountId"] = str(ta.get("id", ""))
            detail["detailToAccountName"] = ta.get("name", "") or ""
            # 转账的本账户概念略模糊,这里把转出账户放在 detailAccountName
            detail["detailAccountId"] = str(fa.get("id", ""))
            detail["detailAccountName"] = fa.get("name", "") or ""
            detail["buyerAcountId"] = str(fa.get("id", ""))
            detail["sellerAcountId"] = str(ta.get("id", ""))
        else:
            return None
        return detail

    # ------------------------------------------------------------------ #
    # 交互式选择 (与老 sui 风格一致)
    # ------------------------------------------------------------------ #
    def printAccounts(self):
        print("神象云账户列表:")
        for acc in self.__accounts:
            print(acc["id"], ":", acc["name"], "(", acc.get("group", ""), acc.get("type", ""), ")")

    def getAccounts(self):
        """返回账户列表 [{id, name, type, balance, group}]。"""
        return self.__accounts

    def getCategories(self):
        """返回 {"income": [...], "payout": [...]},元素含 {id, name, subCat}。"""
        return {"income": self.__incomeCategories, "payout": self.__payoutCategories}

    def selectAccount(self):
        for index, acc in enumerate(self.__accounts):
            print(index, acc["name"])
        accIndex = int(input("请选择账户:"))
        if accIndex >= len(self.__accounts):
            return None
        return self.__accounts[accIndex]

    def __selectCategory(self, categories, label):
        for index, cat in enumerate(categories):
            print(index, cat["name"])
        idx = int(input("请输入%s类型:" % label))
        if idx >= len(categories):
            return None
        cat = categories[idx]
        for index, sub in enumerate(cat["subCat"]):
            print(index, sub["name"])
        subIdx = int(input("请输入%s类型:" % label))
        if subIdx >= len(cat["subCat"]):
            return self.__selectCategory(categories, label)
        return cat["subCat"][subIdx]

    def selectIncomeCategory(self):
        return self.__selectCategory(self.__incomeCategories, "收入")

    def selectPayoutCategory(self):
        return self.__selectCategory(self.__payoutCategories, "支出")
