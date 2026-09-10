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
class LoginBody(BaseModel):
    username: str
    password: str


@app.post("/api/login")
def login(body: LoginBody):
    """用随手记账号密码登录,返回账本列表(神象云 + 旧随手记)。

    同一账号可能同时拥有神象云账本和旧体系账本。设计上:
      - 神象云是「新体系」,默认主账本;登录失败 -> 直接 400,因为新体系挂了什么都做不了
      - 旧体系是「兼容旧账本」,登录失败也不阻塞 —— 该账本从清单里抹掉即可
        (login.sui.com 服务偶尔不可用,但用户大多数操作不需要它)
    """
    try:
        client = sui_service.createClient(body.username, body.password)
        shenxiangBooks = client.getBooks()
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="神象云登录失败: %s" % e)

    user = store.getOrCreateUser(body.username)
    sid = sessions.create()
    s = sessions.get(sid)
    s["username"] = body.username
    s["password"] = body.password      # 仅内存,用于 token 过期后自动重登
    s["userId"] = user["id"]
    s["client"] = client              # 神象云 client(始终保留)
    s["provider"] = PROVIDER_SHENXIANG

    # ---- 旧随手记可选项:登录失败也不影响主流程 ----
    legacyBooks = []
    s["legacyClient"] = None
    try:
        legacyCli = legacy_sui_service.createClient(body.username, body.password)
        s["legacyClient"] = legacyCli
        legacyBooks = legacy_sui_service.listBooks()
    except Exception as e:
        # login.sui.com 不可用 / 验证码风控 / 账号已迁移 —— 都属于「跳过」
        print(f"[legacy] 旧体系登录失败,跳过旧账本选项: {e}")

    # 给神象云账本打 provider 标签
    for b in shenxiangBooks:
        b.setdefault("provider", PROVIDER_SHENXIANG)
    books = shenxiangBooks + legacyBooks

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
def getMapping(sid: str):
    s = getSession(sid)
    return ok(accounts=store.listAccounts(s["userId"]))


class MappingBody(BaseModel):
    sid: str
    accounts: List[dict]


@app.post("/api/mapping")
def saveMapping(body: MappingBody):
    s = getSession(body.sid)
    return ok(accounts=store.saveAccounts(s["userId"], body.accounts))


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
    content = await file.read()
    try:
        data = readers.parseUpload(s["userId"], content, file.filename, bankType)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="账单解析失败: %s" % e)
    s["pending"] = {"source": "upload", "bankno": data["bankno"],
                    "startDate": data["startDate"], "endDate": data["endDate"],
                    "details": data["details"]}
    return ok(bankno=data["bankno"], suiid=data["suiid"],
              startDate=data["startDate"], endDate=data["endDate"],
              count=len(data["details"]), details=data["details"], bankType=bankType)


class ReconcileBody(BaseModel):
    sid: str
    suiid: str


@app.post("/api/reconcile")
def reconcileBills(body: ReconcileBody):
    s = getSession(body.sid)
    client = getClient(body.sid)
    pending = s.get("pending")
    if not pending:
        raise HTTPException(status_code=400, detail="请先导入账单")
    s["pending"]["suiid"] = body.suiid
    provider = s.get("provider", PROVIDER_SHENXIANG)
    try:
        # 旧体系 accountDetail 返回的字段结构与神象云不同,
        # reconcile 引擎找的是 sdate / itemAmount / tranType / *AcountId 命名。
        # 体系直接调用原 Sui.accountDetail 会拿到 raw 数据,这里做一层归一化
        # 让两者走同一条 reconcile 路径,匹配失败时当 unmatched 处理(不报错)。
        rawDetails = client.accountDetail(
            body.suiid,
            reconcile.transDate(pending["startDate"]),
            reconcile.transDate(pending["endDate"]))
        suiDetails = _normalizeLegacyDetails(rawDetails) if provider == PROVIDER_LEGACY else rawDetails
    except Exception as e:
        # 旧体系查询失败,不阻断对账页 —— 用空列表继续
        if provider == PROVIDER_LEGACY:
            print(f"[legacy] 查询旧账本流水失败,继续以空数据对账: {e}")
            suiDetails = []
        else:
            raise HTTPException(status_code=400, detail="查询账本流水失败: %s" % e)
    rules = store.listRules(s["userId"])
    items = reconcile.reconcileDetails(pending["details"], suiDetails,
                                       body.suiid, rules)
    return ok(items=items, suiid=body.suiid, provider=provider)


def _normalizeLegacyDetails(rawDetails):
    """把旧体系的 raw 流水归一化成 shenxiang 风格的字段集。

    旧体系 Sui.accountDetail 返回的就是 report['groups'][].list[] 原样,
    字段名依服务端而定。下面这层映射只为「用户能正常对账」服务,
    缺字段时 fallback 到原值/空 —— 不要让归一化失败抛错。
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
    client = getClient(body.sid)
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

    try:
        if body.op == "payout":
            if provider == PROVIDER_LEGACY:
                # 旧体系没有「记账接口返回 r」概念 —— 直接调用,无返回值校验。
                service.payout(client, body.suiid, amount, body.catid or 0,
                               payTime=payTime, memo=memo)
                r = type("R", (), {"status_code": 200, "text": "legacy: payout ok"})()
            else:
                r = client.payout(body.suiid, amount, body.catid,
                                  payTime=payTime, memo=memo)
        elif body.op == "income":
            if provider == PROVIDER_LEGACY:
                service.income(client, body.suiid, amount, body.catid or 0,
                               payTime=payTime, memo=memo)
                r = type("R", (), {"status_code": 200, "text": "legacy: income ok"})()
            else:
                r = client.income(body.suiid, amount, body.catid,
                                  payTime=payTime, memo=memo)
        elif body.op == "transfer":
            if provider == PROVIDER_LEGACY:
                if detail["transType"] == "income":
                    service.transfer(client, body.opSuiid or 0, body.suiid, amount,
                                    payTime=payTime, memo=memo)
                else:
                    service.transfer(client, body.suiid, body.opSuiid or 0, amount,
                                    payTime=payTime, memo=memo)
                r = type("R", (), {"status_code": 200, "text": "legacy: transfer ok"})()
            else:
                if detail["transType"] == "income":
                    r = client.transfer(body.opSuiid, body.suiid, amount,
                                        payTime=payTime, memo=memo)
                else:
                    r = client.transfer(body.suiid, body.opSuiid, amount,
                                        payTime=payTime, memo=memo)
        else:
            raise HTTPException(status_code=400, detail="未知记账类型: %s" % body.op)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail="记账失败: %s" % e)

    if provider != PROVIDER_LEGACY and r.status_code not in (200, 201):
        raise HTTPException(status_code=400,
                            detail="记账接口返回 %s: %s" % (r.status_code, r.text[:200]))

    if body.saveRule and body.conditions:
        rule = {"conditions": validateConditions(body.conditions), "op": body.op}
        if body.catid:
            rule["catid"] = body.catid
        if body.opSuiid:
            rule["opSuiid"] = body.opSuiid
        if memo:
            rule["memo"] = memo
        store.addRule(s["userId"], rule)

    # 按规则记账的,累加命中次数,便于在管理页看出哪些规则真在用
    if body.ruleId:
        store.recordRuleHit(s["userId"], body.ruleId)
    return ok(message="记账成功", status=getattr(r, "status_code", 200),
              provider=provider)


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
    return ok(rules=store.listRules(s["userId"]))


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
    ruleId = store.addRule(s["userId"], data)
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

    领取即从会话移除(一次性),服务端不留副本 —— 凭据的最终归宿是浏览器。
    """
    s = getSession(body.sid)
    creds = s.pop("gmailCreds", None) if s else None
    if creds is None:
        raise HTTPException(status_code=404, detail="没有待领取的授权凭据")
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
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ok(url=url)


@app.get("/api/gmail/callback")
def gmailCallback(request: Request, code: str = "", state: str = "",
                  error: str = ""):
    """Google OAuth 回调: 换 token 存会话,然后跳回前端。

    生产模式下前端由本服务托管,默认跳回当前访问域名;开发模式(前端 dev server
    在 5173)则用 FRONTEND_URL 环境变量指定跳转地址。
    """
    frontend = os.environ.get("FRONTEND_URL", "")
    if not frontend:
        frontend = str(request.base_url).rstrip("/")
    if error or not code:
        return RedirectResponse("%s/?gmail=error" % frontend)
    s = sessions.get(state)
    if s is None:
        # 会话已过期(授权耗时太久),让用户重新登录
        return RedirectResponse("%s/?gmail=expired" % frontend)
    flow = s.get("gmailFlow")
    if flow is None:
        return RedirectResponse("%s/?gmail=expired" % frontend)
    from server import gmail_service
    try:
        creds = gmail_service.exchangeCode(flow, code)
    except Exception:
        traceback.print_exc()
        return RedirectResponse("%s/?gmail=error" % frontend)
    s["gmailCreds"] = creds
    s.pop("gmailFlow", None)
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
        raise HTTPException(status_code=400, detail="读取邮件失败: %s" % e)
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
