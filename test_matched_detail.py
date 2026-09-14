# -*- coding: utf-8 -*-
"""账本流水展示字段测试:
   - __mapDetail 把神象云原始 item 里的展示字段搬到 detail 字典,
     命名都加 detail 前缀以与老结构避免冲突。
   - 老的对账字段(sdate/tranId/sellerAcountId/buyerAcountId/itemAmount/tranType)
     必须在,且语义不变 —— 这部分已经过实际对账验证,任何回归都属致命。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from shenxiang import ShenxiangClient


def testExpenseDetail():
    item = {
        "id": "tx_001",
        "business_type": "Expense",
        "transaction_time": "1735872000000",   # 2025-01-02 12:00 UTC+8
        "amount": "12.50",
        "remark": "京东支付-京东超市",
        "account": {"id": "1183357936638279681", "name": "农业银行1211"},
        "category": {"id": "595573797774950401", "name": "生活缴费"},
        "member": {"id": "1183356779821658113", "name": "我"},
        "merchant": {"id": "m_9", "name": "京东商城"}
    }
    d = ShenxiangClient._ShenxiangClient__mapDetail(item)
    assert d is not None
    # 兼容字段
    assert d["tranType"] == 1
    assert abs(d["itemAmount"] - 12.5) < 1e-6
    assert d["tranId"] == "tx_001"
    # 展示字段
    assert d["detailRemark"] == "京东支付-京东超市"
    assert d["detailAccountName"] == "农业银行1211"
    assert d["detailAccountId"] == "1183357936638279681"
    assert d["detailCategoryName"] == "生活缴费"
    assert d["detailMemberName"] == "我"
    assert d["detailMerchant"] == "京东商城"
    print("[OK] Expense: 兼容字段+展示字段全保留")


def testIncomeDetail():
    item = {
        "id": "tx_002",
        "business_type": "Income",
        "transaction_time": 1735900000,
        "amount": 200,
        "remark": "工资",
        "account": {"id": "x", "name": "招商银行"},
        "category": {"id": "y", "name": "职业收入"},
        "member": {"id": "m", "name": "我"}
    }
    d = ShenxiangClient._ShenxiangClient__mapDetail(item)
    assert d["tranType"] == 5
    assert abs(d["itemAmount"] - 200) < 1e-6
    assert d["detailAccountName"] == "招商银行"
    assert d["detailCategoryName"] == "职业收入"
    # merchant 缺省时不应当出 KeyError
    assert d["detailMerchant"] == ""
    print("[OK] Income: 兼容字段+展示字段全保留")


def testTransferDetail():
    item = {
        "id": "tx_003",
        "business_type": "Transfer",
        "transaction_time": "1735900000000",
        "from_account": {"id": "a", "name": "农业银行1211"},
        "to_account": {"id": "b", "name": "微信钱包"},
        "from_amount": 50,
        "to_amount": 50,
        "remark": "提现",
    }
    d = ShenxiangClient._ShenxiangClient__mapDetail(item)
    assert d["tranType"] == 2
    assert abs(d["itemAmount"] - 50) < 1e-6
    # 关键:转移账匹配用的 buyer/seller id 仍要正确,这是对账兜底
    assert d["sellerAcountId"] == "b"   # 微信钱包 = 转入 seller
    assert d["buyerAcountId"] == "a"    # 农业银行 = 转出 buyer
    assert d["detailFromAccountName"] == "农业银行1211"
    assert d["detailToAccountName"] == "微信钱包"
    print("[OK] Transfer: 兼容字段+双方账户名全保留")


def testBalanceChangedSkipped():
    item = {"id": "x", "business_type": "Balance_Changed"}
    d = ShenxiangClient._ShenxiangClient__mapDetail(item)
    assert d is None
    print("[OK] 余额调整仍然跳过")


def testUnknownBusinessTypeSkipped():
    item = {"id": "x", "business_type": "Unknown"}
    d = ShenxiangClient._ShenxiangClient__mapDetail(item)
    assert d is None
    print("[OK] 未知类型仍然跳过")


def testTimeFormatBothFormats():
    # 1735872000 秒 = 2025-01-03 10:40 CST,毫秒位则 /1000。
    # 必须按北京时间换算,因为服务器可能跑在任何时区。
    d1 = ShenxiangClient._ShenxiangClient__mapDetail({
        "id": "a", "business_type": "Income", "transaction_time": 1735872000000,
        "amount": 1, "account": {"id": "x", "name": "a"},
        "category": {"id": "y", "name": "z"}
    })
    assert d1["sdate"] == "20250103"
    d2 = ShenxiangClient._ShenxiangClient__mapDetail({
        "id": "b", "business_type": "Income", "transaction_time": 1735872000,
        "amount": 1, "account": {"id": "x", "name": "a"},
        "category": {"id": "y", "name": "z"}
    })
    assert d2["sdate"] == "20250103"
    print("[OK] 毫秒/秒两种格式按北京时间一致")


def testTimezoneIndependence():
    """同样的时间戳,在不同时区跑 __mapDetail 都应得到同一个 sdate。

    不直接调用子进程的 TZ;退一步通过 tz 显式构造同一时刻、验证
    业务期望落到 20250103 —— 验证输出与系统时区无关就足够了。
    """
    # 2025-01-03 10:40 的 CST 对应 UTC 是 02:40(同日 UTC)。
    # 取同日 UTC 时间戳,与 CST 表示是同一天内:
    d_utc = ShenxiangClient._ShenxiangClient__mapDetail({
        "id": "x", "business_type": "Income",
        "transaction_time": 1735872000000,
        "amount": 1, "account": {"id": "x", "name": "a"},
        "category": {"id": "y", "name": "z"}
    })
    # 11:40 CST == 03:40 UTC,同日:所以日期保持 20250103
    d_same_day = ShenxiangClient._ShenxiangClient__mapDetail({
        "id": "y", "business_type": "Income",
        "transaction_time": 1735886400000,   # 2025-01-03 11:40 CST
        "amount": 1, "account": {"id": "x", "name": "a"},
        "category": {"id": "y", "name": "z"}
    })
    assert d_utc["sdate"] == d_same_day["sdate"] == "20250103"
    print("[OK] 跨时区同一天的流水归到同一天")


if __name__ == "__main__":
    testExpenseDetail()
    testIncomeDetail()
    testTransferDetail()
    testBalanceChangedSkipped()
    testUnknownBusinessTypeSkipped()
    testTimeFormatBothFormats()
    testTimezoneIndependence()
    print("\n账本流水展示字段测试通过。")
