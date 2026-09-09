# -*- coding: utf-8 -*-
"""记账时间兜底逻辑的单元测试(纯本地,不联网)。

银行账单部分条目只有日期没有时间,记账时间必须落到该日期的 08:00:00,
而不是当前时间(否则日期会漂到今天)。
"""
from datetime import datetime
from shenxiang import ShenxiangClient
from run import buildPayTime


def msToStr(ms):
    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M:%S")


def main():
    client = ShenxiangClient({})
    toMs = client._ShenxiangClient__payTimeToMs

    cases = [
        ("2026-09-01 :", "只有日期+空时间(农行 xlsx 常见)"),
        ("2026-09-01", "只有日期"),
        ("20260901", "纯数字日期"),
        ("2026-09-01 13:45", "日期+时分"),
        ("2026-09-01 13:45:30", "日期+时分秒"),
        ("20260901134500", "纯数字日期时间"),
        (1788923101426, "毫秒时间戳"),
        ("", "空串"),
        (None, "None"),
        ("2026.09.01", "点分日期"),
    ]
    print("%-22s -> %-20s | %s" % ("输入", "结果", "说明"))
    print("-" * 70)
    ok = True
    for value, desc in cases:
        result = msToStr(toMs(value))
        print("%-22s -> %-20s | %s" % (repr(value), result, desc))

    # 关键断言: 只有日期时必须落到当天 08:00:00
    checks = [
        (toMs("2026-09-01 :"), "2026-09-01 08:00:00"),
        (toMs("2026-09-01"), "2026-09-01 08:00:00"),
        (toMs("20260901"), "2026-09-01 08:00:00"),
        (toMs("2026.09.01"), "2026-09-01 08:00:00"),
        # run.py 层构造的 payTime 同样要正确
        (toMs(buildPayTime("20260901", "")), "2026-09-01 08:00:00"),
        (toMs(buildPayTime("20260901", None)), "2026-09-01 08:00:00"),
        (toMs(buildPayTime("20260901", "1345")), "2026-09-01 13:45:00"),
        (toMs(buildPayTime("20260901", "13:45:30")), "2026-09-01 13:45:00"),
    ]
    print()
    print("断言检查:")
    for actual, expected in checks:
        r = msToStr(actual)
        good = (r == expected)
        ok = ok and good
        print("  [%s] 期望 %s, 实际 %s" % ("OK" if good else "FAIL", expected, r))
    print()
    print("结论:", "全部通过" if ok else "存在失败用例")


if __name__ == "__main__":
    main()
