# -*- coding: utf-8 -*-
"""Gmail 账单服务: 每用户各自 OAuth 授权,凭据只存服务端会话(session)。

与老 gmail.py 的区别:
  - 老版用 run_local_server + token.pickle,单用户、走本地回环
  - 新版是标准 Web OAuth: 后端换 token,凭据放会话内存,不写盘
"""
import os
import sys
import base64

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from googleapiclient.discovery import build                    # noqa: E402
from google_auth_oauthlib.flow import Flow                     # noqa: E402
from google.auth.transport.requests import Request             # noqa: E402
from google_auth_httplib2 import AuthorizedHttp                # noqa: E402
from google.oauth2.credentials import Credentials              # noqa: E402
import httplib2                                                # noqa: E402
import json                                                    # noqa: E402
from email.utils import parsedate_to_datetime                  # noqa: E402

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
CREDENTIALS_PATH = os.environ.get("GOOGLE_CREDENTIALS",
                                  os.path.join(ROOT, "credentials.json"))
REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI",
                              "http://localhost:8000/api/gmail/callback")

# --------------------------------------------------------------------- #
# 代理与超时
#
# Google 的 token 端点 oauth2.googleapis.com 在国内无法直连,必须走代理。
# 用环境变量配置(部署到境外服务器时不设即可):
#     HTTPS_PROXY=socks5://127.0.0.1:10808     # Clash 默认 SOCKS5
#     HTTPS_PROXY=http://127.0.0.1:10809       # Clash 默认 HTTP
#
# requests / requests_oauthlib 会自动读 HTTPS_PROXY,无需额外处理;
# 但 googleapiclient 底层是 httplib2,它不认环境变量,必须显式注入。
# --------------------------------------------------------------------- #
PROXY_URL = (os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
             or os.environ.get("ALL_PROXY") or os.environ.get("all_proxy")
             or "").strip()
GOOGLE_TIMEOUT = float(os.environ.get("GOOGLE_TIMEOUT", "15"))


def proxyInfo():
    """当前代理配置,供诊断用。"""
    return {"proxy": PROXY_URL or "(未配置,直连)", "timeout": GOOGLE_TIMEOUT}


def __http():
    """构造 httplib2.Http,按需挂上代理。

    googleapiclient 不用 requests,所以 here 必须手动把代理塞进去,
    否则「授权成功但读邮件超时」——授权走 requests(认环境变量),读邮件走 httplib2(不认)。
    """
    h = httplib2.Http(timeout=GOOGLE_TIMEOUT)
    if PROXY_URL:
        from urllib.parse import urlparse
        from httplib2 import socks
        p = urlparse(PROXY_URL)
        ptype = (socks.PROXY_TYPE_SOCKS5 if p.scheme.startswith("socks")
                 else socks.PROXY_TYPE_HTTP)
        h.proxy_info = httplib2.ProxyInfo(ptype, p.hostname, p.port)
    return h

# 账单邮件发件人(与 run.py 的路由保持一致)
BILL_SENDERS = [
    "e-statement@creditcard.abchina.com",
    "e-statement@creditcard.abchina.com.cn",
    "ccsvc@message.cmbchina.com",
]


def isConfigured():
    return os.path.exists(CREDENTIALS_PATH)


def buildFlow():
    if not isConfigured():
        raise RuntimeError(
            "缺少 Google OAuth 客户端配置: %s("
            "请在 Google Cloud 创建 OAuth 客户端并下载为该文件)" % CREDENTIALS_PATH)
    return Flow.from_client_secrets_file(
        CREDENTIALS_PATH, SCOPES, redirect_uri=REDIRECT_URI)


def getAuthUrl(flow, state=None):
    """基于一个 flow 实例生成授权地址。state 用来在回调时找回会话(传 sid)。

    注意: flow 实例必须在授权和换 token 两个阶段复用同一个对象——
    新版 google-auth-oauthlib 默认启用 PKCE,code_verifier 存在 flow 里,
    换 token 时如果另建 flow 会因 verifier 不匹配而失败。
    """
    url, _ = flow.authorization_url(
        prompt="consent", access_type="offline",
        include_granted_scopes="true", state=state)
    return url


def exchangeCode(flow, code):
    """用同一个 flow 实例和回调里的 code 换凭据。

    timeout 必须显式传: requests 默认是无限等待,网络不通时要等到系统级
    TCP 超时(Windows 上很久),用户只会看到页面卡住没有任何反馈。
    """
    flow.fetch_token(code=code, timeout=GOOGLE_TIMEOUT)
    return flow.credentials


def refreshIfNeeded(creds):
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


# --------------------------------------------------------------------- #
# 凭据序列化
#
# 默认凭据只活在服务端会话里(进程重启即失效,每次都要重新授权)。
# 用户希望「一次授权长期有效」,所以支持把凭据交给浏览器保存:
#   - credsToJson: 交给前端存本地
#   - credsFromJson: 前端每次请求带回来,后端还原成 Credentials
# access_token 过期时后端会自动用 refresh_token 续期,并把续期后的凭据
# 一并返回,前端覆盖保存即可 —— 所以只要 refresh_token 有效就无需重新授权。
# --------------------------------------------------------------------- #
def credsToJson(creds):
    if creds is None:
        return ""
    return creds.to_json()


def credsFromJson(text):
    """从前端传回的 JSON 还原凭据;格式不对返回 None。"""
    if not text:
        return None
    try:
        info = json.loads(text)
        return Credentials.from_authorized_user_info(info, SCOPES)
    except Exception:
        return None


def buildService(creds):
    """构造 Gmail API client。

    这里必须用带代理的 http(而不是 credentials= 参数): googleapiclient 底层是
    httplib2,不认 HTTPS_PROXY 环境变量。若图省事用 credentials=creds,
    会出现「授权成功、但读邮件超时」这种一半能用一半不能的诡异状态。
    """
    return build("gmail", "v1", http=AuthorizedHttp(creds, http=__http()),
                 cache_discovery=False)


def formatMailDate(value):
    """把 RFC 2822 邮件头日期转成 yyyy/MM/dd。

    邮件头形如 "Wed, 10 Sep 2026 09:00:00 +0800",直接截字符串会在跨时区
    或英文月份时出错,所以按协议解析。带时区的一律换算到本机时区,
    避免海外账单邮件因时差显示成前一天。
    """
    if not value:
        return ""
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is not None:
            dt = dt.astimezone()
        return dt.strftime("%Y/%m/%d")
    except Exception:
        return (value or "")[:10]


def listTallyMails(service, maxResults=30):
    """列出收件箱里的账单邮件(带主题/日期,供用户勾选)。

    labelIds=['INBOX'] 限定只搜收件箱 —— Gmail 的「归档」本质就是移除
    INBOX 标签,所以不加这个限定会把已归档的历史账单也翻出来。
    """
    q = " OR ".join("from:%s" % s for s in BILL_SENDERS)
    results = service.users().messages().list(
        userId="me", q=q, labelIds=["INBOX"], maxResults=maxResults).execute()
    messages = results.get("messages", [])
    out = []
    for m in messages:
        detail = service.users().messages().get(
            userId="me", id=m["id"], format="metadata",
            metadataHeaders=["Subject", "From", "Date"]).execute()
        headers = {h["name"]: h["value"]
                   for h in detail.get("payload", {}).get("headers", [])}
        out.append({
            "id": m["id"],
            "subject": headers.get("Subject", ""),
            "from": headers.get("From", ""),
            "date": formatMailDate(headers.get("Date", "")),
        })
    return out


def __mailContent(messagePart):
    mimeType = messagePart.get("mimeType", "")
    if mimeType.startswith("multipart"):
        for part in messagePart.get("parts", []):
            content = __mailContent(part)
            if content is not None:
                return content
        return None
    if mimeType == "text/html":
        return messagePart.get("body", {}).get("data")
    return None


def getMail(service, messageId):
    """取邮件正文 HTML + 头信息。"""
    mail = service.users().messages().get(userId="me", id=messageId).execute()
    b64 = __mailContent(mail.get("payload", {}))
    if not b64:
        return None
    html = base64.urlsafe_b64decode(b64).decode("utf-8", errors="ignore")
    headers = {h["name"]: h["value"]
               for h in mail.get("payload", {}).get("headers", [])}
    return {
        "id": messageId,
        "From": headers.get("From", ""),
        "To": headers.get("To", ""),
        "Subject": headers.get("Subject", ""),
        "Date": headers.get("Date", ""),
        "data": html,
    }


def createReaderByMail(mail):
    """按发件人路由到对应信用卡账单解析器。"""
    import re
    from ABCCreditReader import ABCCreditReader
    from CMBCreditReader import CMBCreditReader
    fromEmail = ""
    try:
        fromEmail = re.findall("<(.*)>", mail["From"])[0]
    except IndexError:
        fromEmail = mail["From"]
    if fromEmail in ("e-statement@creditcard.abchina.com",
                     "e-statement@creditcard.abchina.com.cn"):
        return ABCCreditReader
    if fromEmail == "ccsvc@message.cmbchina.com":
        return CMBCreditReader
    return None
