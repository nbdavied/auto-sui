# -*- coding: utf-8 -*-
"""账单解析: 复用现有各银行 Reader,接住 Web 上传的文件流。

不再按文件名分发 —— 前端选完账单类型,在请求里带过来。后端落一份
白名单,未知类型直接 400。
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ABCReader import ABCReader          # noqa: E402
from CCBReader import CCBReader          # noqa: E402
from server import store                  # noqa: E402


# 支持的「文件型」账单类型。前端下拉框直接拿这里暴露的列表去渲染。
# 信用卡(ABCCredit/BOC/CMB)等只在邮件里出现,不进上传路径。
FILE_READERS = [
    {"type": "abc", "label": "农业银行 储蓄卡 (abc*.xlsx)"},
    {"type": "ccb", "label": "建设银行 储蓄卡 (hqmx*.xlsx)"},
]

_READER_CLASSES = {"abc": ABCReader, "ccb": CCBReader}


def listFileReaders():
    """给前端下拉用的账单类型清单。"""
    return FILE_READERS


def createReader(bankType, path, config):
    """按用户选择的类型挑对应 Reader,未知类型返回 None。"""
    cls = _READER_CLASSES.get(bankType)
    return cls(config, path) if cls else None


def parseUpload(userId, fileBytes, filename, bankType):
    """解析上传的账单文件。

    bankType —— 用户在页面上选的账单类型,不再看文件名。
    返回 {bankno, suiid, startDate, endDate, details}
    suiid 为空表示该卡号尚未配置账户映射,由前端让用户选择。
    """
    suffix = os.path.splitext(filename)[1] or ".xlsx"
    fd, tmpPath = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(fileBytes)
        config = {"accounts": store.listAccounts(userId)}
        reader = createReader(bankType, tmpPath, config)
        if reader is None:
            supported = "、".join(r["label"] for r in FILE_READERS)
            raise ValueError("不支持的账单类型: '%s'。可选: %s" % (bankType, supported))
        data = reader.analyseData()
        return {
            "bankno": data.get("bankno", ""),
            "suiid": data.get("suiid", ""),
            "startDate": data.get("startDate", ""),
            "endDate": data.get("endDate", ""),
            "details": data.get("details", []),
        }
    finally:
        try:
            os.remove(tmpPath)
        except OSError:
            pass
