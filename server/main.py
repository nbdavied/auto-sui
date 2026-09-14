# -*- coding: utf-8 -*-
"""auto-sui Web 服务入口。

设计原则:
  - 随手记账号密码只出现在请求里,服务端不落库,token 只在会话内存中
  - 复用现有 shenxiang / 各银行 Reader / 对账逻辑,不重复实现
"""
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware                           # noqa: E402
from fastapi.responses import FileResponse, RedirectResponse                 # noqa: E402
from fastapi.staticfiles import StaticFiles                        # noqa: E402
from pydantic import BaseModel                                     # noqa: E402
from typing import Optional, List                                  # noqa: E402

from server import store, session_store as sessions, sui_service, legacy_sui_service  # noqa: E402
from server import readers, reconcile  # noqa: E402

# 提供方常量。前端按这个字段决定到底调哪个后端记账。
PROVIDER_SHENXIANG = "shenxiang"
PROVIDER_LEGACY = "legacy"

app = FastAPI(title="auto-sui 对账服务", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("ALLOW_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WEB_DIST = os.path.join(ROOT, "web", "dist")
# 生产模式前端由本服务托管,默认空即跳回当前域名;开发模式可设为 http://localhost:5173
FRONTEND_URL = os.environ.get("FRONTEND_URL", "")


# --------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------- #
def getSession(sid: str):
    s = sessions.get(sid)
    if s is None:
        raise HTTPException(status_code=401, detail="会话已失效,请重新登录")
    return s


def getClient(sid: str):
    """按当前会话激活的 provider 返回对应 client。

    神象云 client 始终存在 s["client"],旧体系 client 始终存在
    s["legacyClient"] —— 两个字段互不覆盖,避免「切到旧账本后
    再把 s["client"] 顶成 Sui 实例,导致切回神象云时拿错对象」。
    """
    s = getSession(sid)
    provider = s.get("provider", PROVIDER_SHENXIANG)
    if provider == PROVIDER_LEGACY:
        client = s.get("legacyClient")
    else:
        client = s.get("client")
    if client is None:
        raise HTTPException(status_code=401, detail="未登录,请重新登录")
    return client


def getProvider(sid: str):
    """当前会话激活账本的 provider,记账 / 对账 / 列表查询都按它路由。"""
    return getSession(sid).get("provider", PROVIDER_SHENXIANG)


def activeService(provider: str):
    """按 provider 返回 service 模块: shenxiang → sui_service, legacy → legacy_sui_service。

    两个模块的方法形态对齐(createClient / listBooks / selectBook /
    buildAccountOptions / buildCategoryOptions / payout / income /
    transfer)。main.py 通过这一函数把 provider 与 service 解耦,
    不需要在每个 endpoint 里 if/else。
    """
    if provider == PROVIDER_LEGACY:
        return legacy_sui_service
    return sui_service


def ok(**kwargs):
    return {"ok": True, **kwargs}


# --------------------------------------------------------------------- #
# 登录 / 账本
# --------------------------------------------------------------------- #
# --------------------------------------------------------------------- #
# 账本清单
# --------------------------------------------------------------------- #
def _collectShenxiangBooks(client, username=""):
    """神象云账本清单。

    来源: GET yun.feidee.net/cab-index-ws/v3/book-group/cloud
    这些账本由 shenxiang.py 操作。
    """
    books = []
    try:
        for b in client.getBooks() or []:
            bid = b.get("id")
            if bid in (None, ""):
                continue
            books.append({"id": str(bid),
                          "name": b.get("name") or str(bid),
                          "provider": PROVIDER_SHENXIANG})
    except Exception as e:
        print(f"[books] 神象云账本清单获取失败: {e}")
    print(f"[books] {username or '匿名'} 神象云账本 {len(books)} 个: "
          f"{[(b['id'], b['name']) for b in books]}")
    return books


def _collectLegacyBooks(client, username=""):
    """旧随手记账本清单。

    来源: GET tally.feidee.net/mini_program/v1/books/list
    这个接口专门返回旧账本,和神象云那份互不重叠,两边直接拼接即可。

    ⚠️ 这些账本虽然由神象云的 token 才能列出来,但**不能用神象云 client 操作**:
    实测 setBookId(旧账本id) + initTallyInfo 拉回来的账户/分类全是空列表,
    神象云 SDK 只认自己的账本。它们必须路由 provider=legacy 走 sui.py,
    由 book.do?opt=switch 完成真正的账本切换。
    """
    books = []
    try:
        for b in client.listAllBooks():
            books.append({"id": str(b["id"]),
                          "name": b["name"],
                          "provider": PROVIDER_LEGACY})
    except Exception as e:
        print(f"[books] 旧账本清单获取失败: {e}")
    print(f"[books] {username or '匿名'} 旧账本 {len(books)} 个: "
          f"{[(b['id'], b['name']) for b in books]}")
    return books


class LoginBody(BaseModel):
    username: str
    password: str
    # 浏览器会话里已有的神象云 access_token。服务端风控给密码登录加图形码时
    # (code 4099) 用它绕过,不填就走原来的账号密码登录。
    shenxiangToken: str = ""


@app.post("/api/login")
def login(body: LoginBody):
    """登录,返回账本列表(神象云账本 + 旧随手记账本)。

    认证优先级: 账号密码 -> token
      - 神象云是「新体系」,默认主账本;两者都失败 -> 400,因为主体系挂了什么都做不了
      - 旧体系是「兼容旧账本」,登录失败也不阻塞 —— 该账本从清单里抹掉即可
        (login.sui.com 偶尔不可用或触发风控,但用户大多数操作不需要它)

    账本清单来源: 优先 listAllBooks() (小程序接口,能看到旧随手记迁移过来的账本),
    失败则退回 getBooks() (cab-index-ws,只含神象云原生账本)。
    """
    token = (body.shenxiangToken or "").strip()
    client = None
    loginMode = "password"

    if token:
        # token 优先: 风控期密码登录会失败,浏览器里的 token 往往还有效
        client = sui_service.createClientFromToken(token)
        loginMode = "token"
    else:
        try:
            client = sui_service.createClient(body.username, body.password)
        except Exception:
            traceback.print_exc()
            raise HTTPException(
                status_code=400,
                detail="神象云登录失败: %s（可在下方填入 access_token 绕过）" % sys.exc_info()[1])

    # 两个来源各自独立、互不重叠:神象云的走 cab-index-ws,旧账本走 books/list
    books = (_collectShenxiangBooks(client, body.username)
             + _collectLegacyBooks(client, body.username))

    user = store.getOrCreateUser(body.username)
    sid = sessions.create()
    s = sessions.get(sid)
    s["username"] = body.username
    s["password"] = body.password      # 仅内存,用于 token 过期后自动重登
    s["userId"] = user["id"]
    s["client"] = client              # 神象云 client(始终保留)
    s["provider"] = PROVIDER_SHENXIANG
    s["loginMode"] = loginMode
    if token:
        s["token"] = token

    # ---- 旧体系 client: 记账要靠它,登录失败则旧账本不可选 ----
    # 注意 sui.py 的账本切换是 book.do?opt=switch,和上面的清单获取是两回事。
    s["legacyClient"] = None
    try:
        s["legacyClient"] = legacy_sui_service.createClient(
            body.username, body.password)
    except Exception as e:
        # login.sui.com 不可用 / 风控 / 页面结构变化 —— 旧账本就不能记账
        print(f"[legacy] 旧体系登录失败,旧账本不可用: {e}")

    savedBook = user.get("book_id") or ""
    savedProvider = user.get("book_provider", "") or PROVIDER_SHENXIANG
    # 已保存的账本 + 来源 同时匹配 —— 否则 provider 旧数据可能错配
    target = None
    for b in books:
        if b["id"] == savedBook and b.get("provider", PROVIDER_SHENXIANG) == savedProvider:
            target = b
            break
    if target is not None:
        cli = s["legacyClient"] if target["provider"] == PROVIDER_LEGACY else s["client"]
        try:
            activeService(target["provider"]).selectBook(cli, savedBook)
            s["bookId"] = savedBook
            s["provider"] = target["provider"]
        except Exception:
            pass
    return ok(sid=sid, books=books, bookId=s.get("bookId", ""),
              provider=s.get("provider", PROVIDER_SHENXIANG))


class BookBody(BaseModel):
    sid: str
    bookId: str
    provider: Optional[str] = None  # 缺省时按已激活的 provider 路由


@app.post("/api/book")
def selectBook(body: BookBody):
    """切换账本。

    provider 缺省时按现有会话的 provider 走(单 provider 迁移期兼容)。
    同时支持切换「神象云账本 A → 神象云账本 B」(不变 provider,
    只换 bookId);以及「神象云 → 旧随手记」(换 client)。
    """
    s = getSession(body.sid)
    targetProvider = body.provider or s.get("provider", PROVIDER_SHENXIANG)
    if targetProvider not in (PROVIDER_SHENXIANG, PROVIDER_LEGACY):
        raise HTTPException(status_code=400, detail="不支持的账本来源: %s" % targetProvider)
    service = activeService(targetProvider)
    # 选定 provider 后,client 必须对得上
    if targetProvider == PROVIDER_LEGACY:
        cli = s.get("legacyClient")
        if cli is None:
            raise HTTPException(status_code=400,
                                detail="旧体系不可用: 登录时旧账本选项不可选")
    else:
        cli = s.get("client")
    if cli is None:
        raise HTTPException(status_code=401, detail="未登录")

    try:
        service.selectBook(cli, body.bookId)
    except Exception as e:
        raise HTTPException(status_code=400, detail="切换账本失败: %s" % e)
    s["bookId"] = body.bookId
    s["provider"] = targetProvider
    # 不再覆盖 s["client"]:神象云 client 始终在 s["client"]、
    # legacy client 始终在 s["legacyClient"],getClient() 按 provider 路由。
    # 否则「旧账本 → 神象云」切换时会把 s["client"] 顶成 Sui 实例。
    store.setBookId(s["userId"], body.bookId, targetProvider)
    # 切换账本时把「无账本归属」的老规则绑定到这个新账本(若它还没规则),
    # 保证历史规则不丢,且不同账本的规则后续各自独立维护。
    store.adoptOrphansToBook(s["userId"], body.bookId, targetProvider)
    return ok(accounts=service.buildAccountOptions(cli),
              categories=service.buildCategoryOptions(cli),
              bookId=body.bookId, provider=targetProvider)


@app.get("/api/accounts")
def listAccounts(sid: str):
    s = getSession(sid)
    provider = s.get("provider", PROVIDER_SHENXIANG)
    cli = getClient(sid)
    return ok(accounts=activeService(provider).buildAccountOptions(cli),
              provider=provider)


@app.get("/api/categories")
def listCategories(sid: str):
    s = getSession(sid)
    provider = s.get("provider", PROVIDER_SHENXIANG)
    cli = getClient(sid)
    return ok(categories=activeService(provider).buildCategoryOptions(cli),
              provider=provider)


# --------------------------------------------------------------------- #
# 账户映射
# --------------------------------------------------------------------- #
@app.get("/api/mapping")
def getMapping(sid: str, provider: Optional[str] = None):
    """账户映射列表。前端不传 provider 时返回全部(带 provider 字段供区分)。"""
    s = getSession(sid)
    return ok(accounts=store.listAccounts(s["userId"], provider))


class MappingBody(BaseModel):
    sid: str
    accounts: List[dict]
    # 不传表示覆盖当前 provider 下的映射;不写死 'shenxiang' 是为了不在这里
    # 替前端做选择 —— 传什么覆盖什么。
    provider: Optional[str] = None


@app.post("/api/mapping")
def saveMapping(body: MappingBody):
    s = getSession(body.sid)
    return ok(accounts=store.saveAccounts(s["userId"], body.accounts, body.provider))


# --------------------------------------------------------------------- #
# 账单导入与对账
# --------------------------------------------------------------------- #
@app.get("/api/bills/readers")
def listBillReaders():
    """前端「账单类型」下拉的数据源。后端落白名单,不让前端乱传。"""
    from server import readers as _readers
    return ok(readers=_readers.listFileReaders())


@app.post("/api/bills/upload")
async def uploadBill(sid: str = Form(...), bankType: str = Form(...),
                     file: UploadFile = File(...)):
    s = getSession(sid)
    provider = getProvider(sid)
    content = await file.read()
    try:
        data = readers.parseUpload(s["userId"], content, file.filename, bankType, provider)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="账单解析失败: %s" % e)

    # 跨体系陷阱:即便按 provider 取了映射,仍可能出现「映射里的 id 在当前账本里
    # 不存在」—— 比如换了神象云账本、迁移过账户、临时切换到旧账本却用了神象云映射。
    # 这种情况下直接告诉前端 suiid,会让对账查不到流水、记账被服务端拒绝却报成功。
    # 务必在这里核一下 —— 不通过就当「未映射」处理,让用户手选。
    mapped = data.get("suiid") or ""
    if mapped:
        try:
            if not _accountBelongsToCurrentClient(sid, mapped):
                mapped = ""
        except Exception as e:
            print(f"[upload] 校验账户映射异常,按默认处理: {e}")
    data["suiid"] = mapped

    s["pending"] = {"source": "upload", "bankno": data["bankno"],
                    "startDate": data["startDate"], "endDate": data["endDate"],
                    "details": data["details"]}
    return ok(bankno=data["bankno"], suiid=data["suiid"],
              startDate=data["startDate"], endDate=data["endDate"],
              count=len(data["details"]), details=data["details"], bankType=bankType)


def _accountBelongsToCurrentClient(sid: str, accountId: str):
    """当前会话激活账本(由 provider 决定走 shenxiang 还是 sui.py)是否真的存在这个账户。

    shenxiang 和 sui.py 都已把账户缓存在客户端实例里(选账本时拉过),这里只是遍历;
    失败兜底返回 True,允许后续对账/记账自己报错,避免因为校验失败把可用映射也屏蔽掉。
    """
    client = getClient(sid)
    target = str(accountId)
    try:
        if getProvider(sid) == PROVIDER_LEGACY:
            accounts = legacy_sui_service._accounts(client)
        else:
            accounts = client.getAccounts() or []
    except Exception:
        return True
    if not accounts:
        return True
    return any(str(a.get("id", "")) == target for a in accounts)


class ReconcileBody(BaseModel):
    sid: str
    suiid: str


@app.post("/api/reconcile")
def reconcileBills(body: ReconcileBody):
    s = getSession(body.sid)
    pending = s.get("pending")
    if not pending:
        raise HTTPException(status_code=400, detail="请先导入账单")
    s["pending"]["suiid"] = body.suiid
    provider = s.get("provider", PROVIDER_SHENXIANG)

    # 跨体系校验:suiid 必须属于当前账本。否则上一轮的对账结果全是空、记账也被
    # 服务端拒绝 —— 用户看到的是「所有条目都没记账」。直接 400,把锅明确指出来。
    try:
        if not _accountBelongsToCurrentClient(body.sid, body.suiid):
            raise HTTPException(
                status_code=400,
                detail="所选账户不在当前账本里 —— 请在「记账账户」下拉里选正确账户")
    except HTTPException:
        raise
    except Exception:
        pass   # 校验异常不阻断(下面对账/记账会自己报错)

    client = getClient(body.sid)
    try:
        # 旧体系 accountDetail 返回的字段结构与神象云不同,
        # reconcile 引擎找的是 sdate / itemAmount / tranType / *AcountId 命名。
        # 体系直接调用原 Sui.account接口 会拿到 raw 数据,这里做一层归一化
        # 让两者走同一条 reconcile 路径,匹配失败时当 unmatched 处理(不报错)。
        rawDetails = client.accountDetail(
            body.suiid,
            reconcile.transDate(pending["startDate"]),
            reconcile.transDate(pending["endDate"]))
        suiDetails = _normalizeLegacyDetails(rawDetails) if provider == PROVIDER_LEGACY else rawDetails
    except Exception as e:
        # 之前的设计是「旧账本查询失败就静默空列表」 —— 但用户看到的现象就是
        # 「已记账条目没显示」,根本不知道发生了什么。把错误抛上去更直接。
        raise HTTPException(status_code=400, detail="查询账本流水失败: %s" % e)
    rules = store.listRules(s["userId"], s["bookId"], s["provider"])
    items = reconcile.reconcileDetails(pending["details"], suiDetails,
                                       body.suiid, rules)
    return ok(items=items, suiid=body.suiid, provider=provider)


def _normalizeLegacyDetails(rawDetails):
    """把旧体系的 raw 流水归一化成 shenxiang 风格的字段集。

    旧体系 Sui.accountDetail 返回的就是 report['groups'][].list[] 原样,
    字段名依服务端而定。下面这层映射只为「用户能正常对账」服务,
    缺字段时 fallback 到原值/空 —— 不要让归一化失败抛错。

    顺便补齐 detail* 展示字段(MatchedRecord 卡片读取的就是这套) —— 否则旧账本
    下悬停卡片是空白的。语义以神象云 mapDetail 的命名为准:
      - 收支 (type 1/5):本账户 = buyerAcount,无商户概念
      - 转账 (type 2): 转出 = buyerAcount(参考「转支 200000 buyer=农xxx」),
                     转入 = sellerAcount(参考「转支 200000 seller=招行」)。
                     实际语义由对账逻辑反推过:income 命中时 sellerAcountId ==
                     suiid(收款侧),payout 命中时 buyerAcountId == suiid(付款侧)。
    """
    out = []
    for d in rawDetails or []:
        norm = dict(d)
        # sdate 已经在 sui.py 里写过 (YYYYMMDD)
        norm.setdefault("sdate", d.get("sdate", ""))
        # itemAmount / tranType:旧体系里的键名五花八门,做一个模糊查找
        if "itemAmount" not in norm:
            for key in ("price", "money", "amount", "inMoney", "outMoney"):
                if key in d and d[key] not in (None, ""):
                        try:
                            norm["itemAmount"] = float(str(d[key]).replace(",", ""))
                            break
                        except (TypeError, ValueError):
                            pass
        norm.setdefault("itemAmount", 0.0)
        if "tranType" not in norm:
            # 旧体系 inoutType: 1=支出 2=收入 3=转账等
            legacyType = d.get("inoutType", d.get("type", 0))
            try:
                norm["tranType"] = int(legacyType)
            except (TypeError, ValueError):
                norm["tranType"] = 0
        norm.setdefault("tranType", 0)
        # 对手账户 id:sui.py 老接口里通常用 sellerAccountId / buyerAccountId
        norm.setdefault("sellerAcountId", str(d.get("sellerAccountId", "") or ""))
        norm.setdefault("buyerAcountId", str(d.get("buyerAccountId", "") or ""))
        norm.setdefault("tranId", str(d.get("id", d.get("billId", "")) or ""))

        # ---- 展示字段(MatchedRecord 卡片用) ----
        buyerName = d.get("buyerAcount", "") or ""
        sellerName = d.get("sellerAcount", "") or ""
        memo = d.get("memo", "") or d.get("content", "") or ""
        catName = d.get("categoryName", "") or ""
        catId = d.get("categoryId", "") or ""
        # 旧体系 date 是个 dict,里面有 time(毫秒)字段;先尝试它,再退回 sdate。
        ts = ""
        dateInfo = d.get("date")
        if isinstance(dateInfo, dict):
            ts = dateInfo.get("time") or ""
        if not ts and norm.get("sdate"):
            # 兜底:用 08:00 兜一个
            ts = "%s%s080000" % (norm["sdate"][:4], norm["sdate"][4:]) + "0"
            # 不强求毫秒精度,fronted 兼容秒级
        norm["detailRemark"] = memo
        norm["detailCategoryId"] = str(catId)
        norm["detailCategoryName"] = catName
        norm["detailMerchant"] = sellerName if norm["tranType"] in (1, 5) else ""
        norm["detailMemberName"] = d.get("memberName", "") or ""
        norm["detailTransactionTime"] = ts
        if norm["tranType"] == 2:
            # 转账:转出=付款方,转入=收款方(见上方注释)
            norm["detailFromAccountId"] = str(d.get("buyerAcountId", "") or "")
            norm["detailFromAccountName"] = buyerName
            norm["detailToAccountId"] = str(d.get("sellerAcountId", "") or "")
            norm["detailToAccountName"] = sellerName
            norm["detailAccountId"] = norm["detailFromAccountId"]
            norm["detailAccountName"] = buyerName
        else:
            # 收支:本账户 = buyerAcount
            norm["detailAccountId"] = str(d.get("buyerAcountId", "") or "")
            norm["detailAccountName"] = buyerName
            norm["detailFromAccountId"] = norm["detailAccountId"]
            norm["detailFromAccountName"] = buyerName
            norm["detailToAccountId"] = ""
            norm["detailToAccountName"] = ""
        out.append(norm)
    return out


class TallyBody(BaseModel):
    sid: str
    suiid: str
    index: int
    op: str                      # payout / income / transfer
    catid: Optional[str] = None
    opSuiid: Optional[str] = None
    memo: Optional[str] = ""
    saveRule: Optional[bool] = False
    conditions: Optional[List[dict]] = None
    ruleId: Optional[int] = None


@app.post("/api/tally")
def tally(body: TallyBody):
    s = getSession(body.sid)
    pending = s.get("pending")
    if not pending:
        raise HTTPException(status_code=400, detail="请先导入账单")
    details = pending["details"]
    if body.index < 0 or body.index >= len(details):
        raise HTTPException(status_code=400, detail="条目不存在")
    detail = details[body.index]
    payTime = reconcile.buildPayTime(detail["date"], detail.get("time"))
    memo = body.memo if body.memo is not None else detail.get("memo", "")
    amount = detail["amount"]
    provider = s.get("provider", PROVIDER_SHENXIANG)
    service = activeService(provider)

    # 旧账本:service.payout/income/transfer 已经把响应体校验过(成功返回 dict,
    # 失败 raise RuntimeError);神象云:client 直接返回 Response,自己看 status_code。
    # 两者都走同一个 try/except,失败统一 400,避免「记账被服务端拒绝却报成功」。
    client = getClient(body.sid)
    status_code = 0
    try:
        if body.op == "payout":
            r = service.payout(client, body.suiid, amount, body.catid,
                               payTime=payTime, memo=memo)
        elif body.op == "income":
            r = service.income(client, body.suiid, amount, body.catid,
                               payTime=payTime, memo=memo)
        elif body.op == "transfer":
            if detail["transType"] == "income":
                r = service.transfer(client, body.opSuiid or 0, body.suiid, amount,
                                     payTime=payTime, memo=memo)
            else:
                r = service.transfer(client, body.suiid, body.opSuiid or 0, amount,
                                     payTime=payTime, memo=memo)
        else:
            raise HTTPException(status_code=400, detail="未知记账类型: %s" % body.op)
        status_code = getattr(r, "status_code", 200) or 200
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail="记账失败: %s" % e)

    if status_code not in (200, 201):
        raise HTTPException(status_code=400,
                            detail="记账接口返回 %s: %s" % (status_code, str(r)[:200]))

    if body.saveRule and body.conditions:
        rule = {"conditions": validateConditions(body.conditions), "op": body.op}
        if body.catid:
            rule["catid"] = body.catid
        if body.opSuiid:
            rule["opSuiid"] = body.opSuiid
        if memo:
            rule["memo"] = memo
        store.addRule(s["userId"], rule, s["bookId"], s["provider"])

    # 按规则记账的,累加命中次数,便于在管理页看出哪些规则真在用
    if body.ruleId:
        store.recordRuleHit(s["userId"], body.ruleId)
    return ok(message="记账成功", status=status_code, provider=provider)


# --------------------------------------------------------------------- #
# 规则
# --------------------------------------------------------------------- #
def validateConditions(conds):
    """校验结构化条件。

    字段和匹配方式都过白名单 —— 规则来自用户输入,绝不能把任意内容
    带到匹配环节(老版本用 eval 执行表达式,等于开放任意代码执行)。
    """
    from server.reconcile import MATCH_FIELDS, MATCH_KINDS
    if not conds:
        raise HTTPException(status_code=400, detail="至少需要一个匹配条件")
    out = []
    for c in conds:
        if not isinstance(c, dict):
            raise HTTPException(status_code=400, detail="条件格式不正确")
        field = str(c.get("field", ""))
        kind = str(c.get("match", ""))
        value = c.get("value", "")
        if field not in MATCH_FIELDS:
            raise HTTPException(status_code=400, detail="不支持的匹配字段: %s" % field)
        if kind not in MATCH_KINDS:
            raise HTTPException(status_code=400, detail="不支持的匹配方式: %s" % kind)
        if str(value).strip() == "":
            raise HTTPException(status_code=400, detail="匹配值不能为空")
        out.append({"field": field, "match": kind, "value": str(value)[:200]})
    return out


@app.get("/api/rules")
def getRules(sid: str):
    s = getSession(sid)
    # 先把无账本归属的老规则绑定到当前账本(若它还没规则),再只返回当前账本的规则
    store.adoptOrphansToBook(s["userId"], s.get("bookId", ""), s.get("provider", PROVIDER_SHENXIANG))
    return ok(rules=store.listRules(s["userId"], s["bookId"], s["provider"]))


class RuleBody(BaseModel):
    sid: str
    conditions: List[dict]
    op: str
    catid: Optional[str] = None
    opSuiid: Optional[str] = None
    memo: Optional[str] = None
    priority: Optional[int] = 0


@app.post("/api/rules")
def addRule(body: RuleBody):
    s = getSession(body.sid)
    data = body.dict(exclude={"sid"})
    data["conditions"] = validateConditions(data["conditions"])
    ruleId = store.addRule(s["userId"], data, s["bookId"], s["provider"])
    return ok(id=ruleId)


class RuleUpdateBody(BaseModel):
    sid: str
    conditions: Optional[List[dict]] = None
    op: Optional[str] = None
    catid: Optional[str] = None
    opSuiid: Optional[str] = None
    memo: Optional[str] = None
    priority: Optional[int] = None


@app.put("/api/rules/{ruleId}")
def updateRule(ruleId: int, body: RuleUpdateBody):
    s = getSession(body.sid)
    data = body.dict(exclude={"sid"})
    data = {k: v for k, v in data.items() if v is not None}
    if "conditions" in data:
        data["conditions"] = validateConditions(data["conditions"])
    if not data:
        raise HTTPException(status_code=400, detail="没有要更新的内容")
    if not store.updateRule(s["userId"], ruleId, data):
        raise HTTPException(status_code=404, detail="规则不存在")
    return ok()


@app.delete("/api/rules/{ruleId}")
def delRule(ruleId: int, sid: str):
    s = getSession(sid)
    store.deleteRule(s["userId"], ruleId)
    return ok()


# --------------------------------------------------------------------- #
# Gmail
# --------------------------------------------------------------------- #
def resolveGmailCreds(s, credsJson=None):
    """取本次请求要用的 Gmail 凭据。

    优先用浏览器传回来的凭据(持久化在浏览器,跨登录/跨进程都有效);
    没传则退回会话内的凭据(刚授权完、还没被领走的那一瞬)。
    """
    from server import gmail_service
    creds = gmail_service.credsFromJson(credsJson)
    if creds is not None:
        return creds
    return s.get("gmailCreds")


class GmailClaimBody(BaseModel):
    sid: str


@app.post("/api/gmail/claim")
def gmailClaim(body: GmailClaimBody):
    """授权完成后,前端来把凭据领走存到浏览器。

    从会话移除(一次性),服务端不再留副本 —— 凭据的最终归宿是浏览器。
    同时刷一次落盘,避免「领走了但还没落盘」时进程重启导致凭据丢失。
    """
    s = getSession(body.sid)
    creds = s.pop("gmailCreds", None) if s else None
    if creds is None:
        raise HTTPException(status_code=404, detail="没有待领取的授权凭据")
    sessions.setField(body.sid, "gmailCredsClaimed", True)
    from server import gmail_service
    return ok(creds=gmail_service.credsToJson(creds))


@app.get("/api/gmail/status")
def gmailStatus(sid: str):
    s = getSession(sid)
    from server import gmail_service
    # proxy 一并返回: 国内网络下 Gmail 授权失败多半是没配代理
    return ok(authorized=bool(s and s.get("gmailCreds")),
              configured=gmail_service.isConfigured(),
              proxy=gmail_service.proxyInfo())


@app.get("/api/gmail/auth-url")
def gmailAuthUrl(sid: str):
    s = getSession(sid)
    from server import gmail_service
    try:
        # flow 实例要跨「授权 → 换 token」复用,先存进会话
        flow = gmail_service.buildFlow()
        s["gmailFlow"] = flow
        # state 带 sid,回调时用它找回同一个会话
        url = gmail_service.getAuthUrl(flow, state=sid)
        # 注意顺序: PKCE 的 code_verifier 是在 authorization_url() 里才生成的,
        # 必须等 URL 出来之后再抽存,否则存进去的是 None ——
        # 那样重启后无法重建 flow,回调照样报「授权会话已失效」。
        sessions.setField(sid, "gmailFlowState", gmail_service.flowToState(flow))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ok(url=url)


@app.get("/api/gmail/callback")
def gmailCallback(request: Request, code: str = "", state: str = "",
                  error: str = ""):
    """Google OAuth 回调: 换 token 存会话,然后跳回前端。

    生产模式下前端由本服务托管,默认跳回当前访问域名;开发模式(前端 dev server
    在 5173)则用 FRONTEND_URL 环境变量指定跳转地址。

    会话恢复: 用户可能要在 Google 页面上停留很久,期间服务若重启,内存里的
    flow 对象就没了。此时用落盘的 gmailFlowState(PKCE code_verifier)重建 flow,
    让这一次授权仍然能完成 —— 否则用户只能反复重试,表现得就像「授权坏了」。
    """
    frontend = os.environ.get("FRONTEND_URL", "")
    if not frontend:
        frontend = str(request.base_url).rstrip("/")
    if error:
        return RedirectResponse("%s/?gmail=error&reason=%s" % (frontend, error))
    if not code:
        return RedirectResponse("%s/?gmail=error&reason=missing_code" % frontend)
    s = sessions.get(state)
    if s is None:
        # 会话彻底没了(超过 8 小时 TTL / 落盘文件被删),只能重新授权
        return RedirectResponse("%s/?gmail=expired" % frontend)
    from server import gmail_service
    flow = s.get("gmailFlow")
    if flow is None:
        # 进程重启过: 用落盘的 verifier 重建 flow
        flow = gmail_service.flowFromState(s.get("gmailFlowState"))
    if flow is None:
        return RedirectResponse("%s/?gmail=expired" % frontend)
    try:
        creds = gmail_service.exchangeCode(flow, code)
    except Exception:
        traceback.print_exc()
        return RedirectResponse("%s/?gmail=error" % frontend)
    s.pop("gmailFlow", None)
    s.pop("gmailFlowState", None)
    sessions.setField(state, "gmailCreds", creds)
    return RedirectResponse("%s/?gmail=ok&sid=%s" % (frontend, state))


class GmailMailsBody(BaseModel):
    sid: str
    creds: Optional[str] = None
    maxResults: int = 30


@app.post("/api/gmail/mails")
def gmailMails(body: GmailMailsBody):
    """列账单邮件。凭据由浏览器提供,续期后回传新凭据供前端覆盖保存。"""
    s = getSession(body.sid)
    creds = resolveGmailCreds(s, body.creds)
    if not creds:
        raise HTTPException(status_code=401, detail="Gmail 未授权")
    from server import gmail_service
    try:
        creds = gmail_service.refreshIfNeeded(creds)
    except Exception:
        # refresh_token 被撤销/过期: 前端据此清除本地凭据并引导重新授权
        raise HTTPException(status_code=401, detail="Gmail 授权已失效，请重新授权")
    try:
        service = gmail_service.buildService(creds)
        mails = gmail_service.listTallyMails(service, body.maxResults)
    except Exception as e:
        # 把真实异常打进服务端日志(journald 只看得到 400 状态行,看不到响应体),
        # 并带上当前代理配置,便于区分: 本地 DNS 超时 / 代理连不通 / SSL 错误
        traceback.print_exc()
        pinfo = gmail_service.proxyInfo()
        raise HTTPException(
            status_code=400,
            detail="读取邮件失败[%s via %s]: %s: %s"
            % (type(e).__name__, pinfo.get("proxy"), type(e).__module__, e))
    return ok(mails=mails, creds=gmail_service.credsToJson(creds))


class GmailLoadBody(BaseModel):
    sid: str
    messageIds: List[str]
    suiid: Optional[str] = None
    creds: Optional[str] = None


@app.post("/api/gmail/load")
def gmailLoad(body: GmailLoadBody):
    s = getSession(body.sid)
    creds = resolveGmailCreds(s, body.creds)
    if not creds:
        raise HTTPException(status_code=401, detail="Gmail 未授权")
    from server import gmail_service
    try:
        creds = gmail_service.refreshIfNeeded(creds)
    except Exception:
        raise HTTPException(status_code=401, detail="Gmail 授权已失效，请重新授权")
    service = gmail_service.buildService(creds)

    details = []
    bankno = ""
    startDate, endDate = "", ""
    for mid in body.messageIds:
        mail = gmail_service.getMail(service, mid)
        if not mail:
            continue
        readerCls = gmail_service.createReaderByMail(mail)
        if readerCls is None:
            continue
        config = {"accounts": store.listAccounts(s["userId"])}
        data = readerCls(config, mail).analyseData()
        for d in data.get("details", []):
            d["messageId"] = mid
            d["subject"] = mail.get("Subject", "")
            details.append(d)
        bankno = bankno or data.get("bankno", "")
        startDate = startDate or data.get("startDate", "")
        endDate = endDate or data.get("endDate", "")

    if not details:
        raise HTTPException(status_code=400, detail="所选邮件中没有识别到账单")

    s["pending"] = {"source": "gmail", "bankno": bankno,
                    "startDate": startDate, "endDate": endDate,
                    "details": details}
    return ok(bankno=bankno, suiid=body.suiid or "",
              startDate=startDate, endDate=endDate,
              count=len(details), details=details,
              creds=gmail_service.credsToJson(creds))


@app.get("/api/health")
def health():
    return ok(service="auto-sui", version="1.0.0")


# --------------------------------------------------------------------- #
# 前端静态资源(生产构建后)
# 注意: 静态挂载必须放在所有 API 路由之后,否则会吃掉 /api 请求
# --------------------------------------------------------------------- #
if os.path.isdir(WEB_DIST):
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
