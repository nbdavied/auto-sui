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

from server import store, session_store as sessions, sui_service, readers, reconcile  # noqa: E402

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
    s = getSession(sid)
    client = s.get("client")
    if client is None:
        raise HTTPException(status_code=401, detail="未登录神象云,请重新登录")
    return client


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
    """用随手记账号密码登录,返回账本列表。密码不会写入任何持久化存储。"""
    try:
        client = sui_service.createClient(body.username, body.password)
        books = client.getBooks()
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="神象云登录失败: %s" % e)

    user = store.getOrCreateUser(body.username)
    sid = sessions.create()
    s = sessions.get(sid)
    s["username"] = body.username
    s["password"] = body.password      # 仅内存,用于 token 过期后自动重登
    s["userId"] = user["id"]
    s["client"] = client

    savedBook = user.get("book_id") or ""
    # 已保存过账本则直接进入
    if savedBook and any(b["id"] == savedBook for b in books):
        try:
            sui_service.selectBook(client, savedBook)
            s["bookId"] = savedBook
        except Exception:
            pass
    return ok(sid=sid, books=books, bookId=s.get("bookId", ""))


class BookBody(BaseModel):
    sid: str
    bookId: str


@app.post("/api/book")
def selectBook(body: BookBody):
    s = getSession(body.sid)
    client = s.get("client")
    if client is None:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        info = sui_service.selectBook(client, body.bookId)
    except Exception as e:
        raise HTTPException(status_code=400, detail="切换账本失败: %s" % e)
    s["bookId"] = body.bookId
    store.setBookId(s["userId"], body.bookId)
    return ok(accounts=sui_service.buildAccountOptions(client),
              categories=sui_service.buildCategoryOptions(client),
              bookId=body.bookId)


@app.get("/api/accounts")
def listAccounts(sid: str):
    client = getClient(sid)
    return ok(accounts=sui_service.buildAccountOptions(client))


@app.get("/api/categories")
def listCategories(sid: str):
    client = getClient(sid)
    return ok(categories=sui_service.buildCategoryOptions(client))


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
@app.post("/api/bills/upload")
async def uploadBill(sid: str = Form(...), file: UploadFile = File(...)):
    s = getSession(sid)
    content = await file.read()
    try:
        data = readers.parseUpload(s["userId"], content, file.filename)
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
              count=len(data["details"]), details=data["details"])


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
    try:
        suiDetails = client.accountDetail(
            body.suiid,
            reconcile.transDate(pending["startDate"]),
            reconcile.transDate(pending["endDate"]))
    except Exception as e:
        raise HTTPException(status_code=400, detail="查询账本流水失败: %s" % e)
    rules = store.listRules(s["userId"])
    items = reconcile.reconcileDetails(pending["details"], suiDetails,
                                       body.suiid, rules)
    return ok(items=items, suiid=body.suiid)


class TallyBody(BaseModel):
    sid: str
    suiid: str
    index: int
    op: str                      # payout / income / transfer
    catid: Optional[str] = None
    opSuiid: Optional[str] = None
    memo: Optional[str] = ""
    saveRule: Optional[bool] = False
    exp: Optional[str] = None


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

    try:
        if body.op == "payout":
            r = client.payout(body.suiid, amount, body.catid, payTime=payTime, memo=memo)
        elif body.op == "income":
            r = client.income(body.suiid, amount, body.catid, payTime=payTime, memo=memo)
        elif body.op == "transfer":
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

    if r.status_code not in (200, 201):
        raise HTTPException(status_code=400,
                            detail="记账接口返回 %s: %s" % (r.status_code, r.text[:200]))

    if body.saveRule and body.exp:
        rule = {"exp": body.exp, "op": body.op}
        if body.catid:
            rule["catid"] = body.catid
        if body.opSuiid:
            rule["opSuiid"] = body.opSuiid
        if memo:
            rule["memo"] = memo
        store.addRule(s["userId"], rule)
    return ok(message="记账成功", status=r.status_code)


# --------------------------------------------------------------------- #
# 规则
# --------------------------------------------------------------------- #
@app.get("/api/rules")
def getRules(sid: str):
    s = getSession(sid)
    return ok(rules=store.listRules(s["userId"]))


class RuleBody(BaseModel):
    sid: str
    exp: str
    op: str
    catid: Optional[str] = None
    opSuiid: Optional[str] = None
    memo: Optional[str] = None


@app.post("/api/rules")
def addRule(body: RuleBody):
    s = getSession(body.sid)
    ruleId = store.addRule(s["userId"], body.dict(exclude={"sid"}))
    return ok(id=ruleId)


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
