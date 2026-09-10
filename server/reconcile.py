# -*- coding: utf-8 -*-
"""对账引擎: 从 run.py 抽出的公共逻辑,Web 与命令行共用。

核心判定: 银行流水与账本流水按「日期 + 金额 + 收支方向」匹配。
判定一致(不重复记账)、判定不一致(触发记账),是整个自动记账的地基。
"""
import re
import json

# 账单里部分条目只有日期没有时间,统一按 08:00 记账,避免日期漂到今天
DEFAULT_TIME = "0800"

# --------------------------------------------------------------------- #
# 规则匹配(结构化条件)
#
# 规则原来是 exp 表达式 + eval 执行。多用户部署时,任何登录用户都能借规则
# 表达式执行任意代码(读服务器文件、枚举数据),所以改成结构化条件:
#   条件 = {field, match, value},多个条件之间 AND
# 字段和匹配方式都用白名单,不使用 eval。
# --------------------------------------------------------------------- #
MATCH_FIELDS = ["opAccName", "opAccNo", "memo", "usage", "amount", "transType"]

MATCH_KINDS = ["eq", "contains", "startswith", "regex", "gt", "lt"]

MATCH_LABELS = {
    "eq": "等于",
    "contains": "包含",
    "startswith": "开头是",
    "regex": "正则",
    "gt": "大于",
    "lt": "小于",
}

FIELD_LABELS = {
    "opAccName": "对手户名",
    "opAccNo": "对手账号",
    "memo": "备注",
    "usage": "用途",
    "amount": "金额",
    "transType": "收支方向",
}

# 用户提供的正则可能触发灾难性回溯,限制长度
REGEX_MAX_LEN = 120


def matchCondition(field, kind, target, actual):
    """单条条件是否命中。任何异常都按未命中处理,不让坏规则影响对账。"""
    if field not in MATCH_FIELDS or kind not in MATCH_KINDS:
        return False
    actual = "" if actual is None else str(actual)
    target = "" if target is None else str(target)
    try:
        if kind == "eq":
            return actual == target
        if kind == "contains":
            return target in actual
        if kind == "startswith":
            return actual.startswith(target)
        if kind == "regex":
            if len(target) > REGEX_MAX_LEN:
                return False
            return re.search(target, actual) is not None
        if kind in ("gt", "lt"):
            a, b = float(actual), float(target)
            return a > b if kind == "gt" else a < b
    except Exception:
        return False
    return False


def parseConditions(raw):
    """解析规则里的 conditions(JSON 字符串或列表),失败返回 []。"""
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def expToConditions(exp):
    """把老式表达式转译成结构化条件(迁移用)。

    只认 `字段 == '值' and ...` 这种自动生成的形式;
    识别不出来的部分直接丢弃 —— 宁可丢规则,也不保留可执行代码。
    """
    conds = []
    if not exp:
        return conds
    for m in re.finditer(r"(\w+)\s*==\s*(['\"])(.*?)\2", exp):
        field, value = m.group(1), m.group(3)
        if field in MATCH_FIELDS:
            conds.append({"field": field, "match": "eq", "value": value})
    return conds


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


def matchRule(rule, detail):
    """规则是否命中这条银行流水。所有条件都命中才算命中(AND)。"""
    conds = parseConditions(rule.get("conditions"))
    if not conds:
        return False
    for c in conds:
        if not isinstance(c, dict):
            return False
        field = c.get("field", "")
        actual = detail.get(field, "")
        if not matchCondition(field, c.get("match", ""), c.get("value", ""), actual):
            return False
    return True


def checkRules(rules, detail, suiid=None):
    """按优先级从高到低找第一条命中的规则。

    同一条流水可能被多条规则命中,优先级高的胜出,保证记账结果可预期。
    """
    ordered = sorted(rules, key=lambda r: -(r.get("priority") or 0))
    for rule in ordered:
        try:
            if matchRule(rule, detail):
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
