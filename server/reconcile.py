# -*- coding: utf-8 -*-
"""对账引擎: 从 run.py 抽出的公共逻辑,Web 与命令行共用。

核心判定: 银行流水与账本流水按「日期 + 金额 + 收支方向」匹配。
判定一致(不重复记账)、判定不一致(触发记账),是整个自动记账的地基。
"""
import re

# 账单里部分条目只有日期没有时间,统一按 08:00 记账,避免日期漂到今天
DEFAULT_TIME = "0800"


def buildPayTime(date, time):
    """组装 'YYYY-MM-DD HH:MM'。时间缺失时补 08:00。"""
    t = (time or "").replace(":", "")
    if len(t) < 4:
        t = DEFAULT_TIME
    return "%s-%s-%s %s:%s" % (date[0:4], date[4:6], date[6:8], t[0:2], t[2:4])


def transDate(date):
    return date[0:4] + "." + date[4:6] + "." + date[6:8]


def determAmount(bankDetail, suiDetail):
    return bankDetail["amount"] == format(suiDetail["itemAmount"], "0.2f")


def isMatchedDetail(bankDetail, suiDetail, suiid):
    """银行流水与账本流水是否同一笔。"""
    if bankDetail["date"] != suiDetail["sdate"]:
        return False
    if not determAmount(bankDetail, suiDetail):
        return False
    transType = bankDetail["transType"]
    if transType == "income":
        if suiDetail["tranType"] == 5:
            return True
        if suiDetail["tranType"] == 2 and str(suiDetail["sellerAcountId"]) == suiid:
            return True
    if transType == "payout":
        if suiDetail["tranType"] == 1:
            return True
        if suiDetail["tranType"] == 2 and str(suiDetail["buyerAcountId"]) == suiid:
            return True
    return False


def findSuiDetail(bankDetail, suiDetails, suiid):
    for suiDetail in suiDetails:
        if isMatchedDetail(bankDetail, suiDetail, suiid):
            return suiDetail
    return None


def checkRules(rules, detail, suiid):
    """按规则表达式匹配,返回命中的规则。"""
    amount = detail["amount"]
    transType = detail["transType"]
    opAccNo = detail.get("opAccNo", "") or ""
    opAccName = detail.get("opAccName", "") or ""
    usage = detail.get("usage", "") or ""
    memo = detail.get("memo", "") or ""
    for rule in rules:
        try:
            if eval(rule["exp"]):  # noqa: S307 - 规则表达式由用户自己配置
                return rule
        except Exception:
            continue
    return None


def reconcileDetails(bankDetails, suiDetails, suiid, rules=None):
    """给每条银行流水标注状态。

    返回每条:
      status: 'matched' 已入账 / 'auto' 规则可自动记账 / 'manual' 需人工判断
      matched: 命中的账本流水
      rule:    命中的规则
    """
    rules = rules or []
    result = []
    for bankDetail in bankDetails:
        item = dict(bankDetail)
        matched = findSuiDetail(bankDetail, suiDetails, suiid)
        if matched is not None:
            item["status"] = "matched"
            item["matched"] = matched
        else:
            rule = checkRules(rules, bankDetail, suiid)
            item["status"] = "auto" if rule else "manual"
            item["rule"] = rule
        result.append(item)
    return result


def detectReaderType(filename):
    """按文件名判断用哪个账单解析器。"""
    name = filename.lower()
    if name.startswith("abc"):
        return "abc_debit"
    if name.startswith("hqmx"):
        return "ccb_debit"
    return None
