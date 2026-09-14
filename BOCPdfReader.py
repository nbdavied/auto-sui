# -*- coding: utf-8 -*-
"""中国银行信用卡 PDF 账单解析器。

中行从某时起把信用卡账单改为「PDF 附件」形式发送(发件人 boczhangdan@bankofchina.com,
标题「中国银行信用卡电子账单」),老的 BOCCreditReader 解析的是更早的 HTML 邮件正文,
对中行已失效。本 reader 直接解析 PDF 附件。

依赖: pdfplumber(从 Gmail 附件字节流解析,不落盘)。

输出结构与 ABCCreditReader / CMBCreditReader 保持一致,便于 gmailLoad 统一处理:
    {bankno, suiid, startDate, endDate, details:[...]}
"""
from bankReader import BankReader
import re
import io
from datetime import datetime, timedelta
from monthdelta import monthdelta
import pdfplumber

# PDF 里卡号形如 "4662 4533 **** 7513"(带空格),conf.json 里存的是 "46624533****7513"(无空格)
CARD_RE = re.compile(r"(\d{4}\s+\d{4}\s+\*{4}\s+\d{4})")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class BOCPdfReader(BankReader):
    __mail = None

    def __init__(self, config, mail):
        super().__init__(config)
        self.__mail = mail

    def analyseData(self):
        pdf_bytes = self.__pick_pdf()
        if not pdf_bytes:
            raise ValueError("邮件中没有找到 PDF 账单附件")

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            closing = self.__find_closing_date(pdf)
            cards = self.__find_cards(pdf)        # {last4: 完整卡号(带空格)}
            details = self.__extract_transactions(pdf, cards)

        if not closing:
            raise ValueError("未能从 PDF 中识别账单日(Statement Closing Date)")
        if not cards:
            raise ValueError("未能从 PDF 中识别信用卡卡号")
        if not details:
            raise ValueError("PDF 中未找到交易明细")

        tally = datetime.strptime(closing, "%Y-%m-%d")
        # 账单周期 = 上一账单日 +1 天 ~ 本期账单日(与随手记对账窗口对齐)
        startDate = (tally - monthdelta(1) + timedelta(days=1)).strftime("%Y%m%d")
        endDate = tally.strftime("%Y%m%d")

        # 账户映射: 合并账单通常同一持卡人,取第一张卡定位 suiid。
        # 多卡时每张交易已在 detail 里带自己的 bankno,见 __extract_transactions。
        first_card = next(iter(cards.values()))
        bankno = self.__norm_card(first_card)
        accountInfo = self.getAccountInfo(bankno)
        suiid = accountInfo["suiid"]

        return {
            "bankno": bankno,
            "suiid": suiid,
            "startDate": startDate,
            "endDate": endDate,
            "details": details,
        }

    # ------------------------------------------------------------------ #
    # 内部辅助
    # ------------------------------------------------------------------ #
    @staticmethod
    def __norm_card(card):
        """去掉空格,把 '4662 4533 **** 7513' -> '46624533****7513',
        与 conf.json / store.accounts 里的 bankno 对齐。"""
        return re.sub(r"\s+", "", card or "")

    def __pick_pdf(self):
        """从邮件附件里挑第一个 PDF。"""
        attachments = self.__mail.get("attachments") or []
        for att in attachments:
            fn = (att.get("filename") or "").lower()
            mime = (att.get("mimeType") or "").lower()
            if fn.endswith(".pdf") or "pdf" in mime:
                if att.get("data"):
                    return att["data"]
        # 兜底: 只有一个附件且是 PDF 但没标 mime
        if len(attachments) == 1 and attachments[0].get("data"):
            return attachments[0]["data"]
        return None

    @staticmethod
    def __find_closing_date(pdf):
        """从第一页 Account Summary 表里取账单日(Statement Closing Date)。"""
        for page in pdf.pages:
            for t in page.extract_tables():
                flat = [c or "" for r in t for c in r]
                if any("账单日" in c for c in flat):
                    for r in t:
                        for i, c in enumerate(r):
                            if c and "账单日" in c:
                                if len(t) > 1 and i < len(t[1]):
                                    val = (t[1][i] or "").strip()
                                    if DATE_RE.match(val):
                                        return val
        return None

    @staticmethod
    def __find_cards(pdf):
        """返回 {卡号后四位: 完整卡号(带空格)}。"""
        cards = {}
        for page in pdf.pages:
            for t in page.extract_tables():
                for r in t:
                    for c in r:
                        if c and CARD_RE.search(c):
                            full = CARD_RE.search(c).group(1)
                            last4 = full.split()[-1]
                            cards[last4] = full
        return cards

    @staticmethod
    def __is_txn_table(t):
        flat = " ".join(c or "" for r in t for c in r)
        return ("交易日" in flat) and ("交易描述" in flat) and ("支出" in flat)

    def __extract_transactions(self, pdf, cards):
        details = []
        for page in pdf.pages:
            for t in page.extract_tables():
                if not self.__is_txn_table(t):
                    continue
                for r in t[1:]:               # 跳过表头
                    if len(r) < 6:
                        continue
                    txn_date, _, last4, desc, deposit, expend = \
                        [(c or "").strip() for c in r[:6]]
                    if not txn_date or not DATE_RE.match(txn_date):
                        continue
                    if deposit and not expend:
                        transType, amount = "income", deposit
                    elif expend and not deposit:
                        transType, amount = "payout", expend
                    else:
                        continue
                    # 去掉因 PDF 换行被拆开的 "6.770 1" 这类数字空格
                    memo = re.sub(r"(\d)\s+(\d)", r"\1\2",
                                  re.sub(r"\s+", " ", desc)).strip()
                    card_full = cards.get(last4, "")
                    details.append({
                        "date": txn_date.replace("-", ""),
                        "time": "080000",
                        "amount": amount,
                        "balance": 0,
                        "opAccName": "",
                        "opAccNo": "",
                        "transBank": "",
                        "channel": "",
                        "transType": transType,
                        "usage": "",
                        "memo": memo,
                        # 多卡合并账单时,每条交易带上自己归属的卡号(已归一化)
                        "bankno": self.__norm_card(card_full),
                    })
        return details
