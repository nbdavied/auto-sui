# -*- coding: utf-8 -*-
"""账单解析: 复用现有各银行 Reader,接住 Web 上传的文件流。"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ABCReader import ABCReader          # noqa: E402
from CCBReader import CCBReader          # noqa: E402
from server import store                  # noqa: E402


def createReader(filename, path, config):
    """与 run.py 保持一致的按文件名前缀路由。"""
    name = filename.lower()
    if name.startswith("abc"):
        return ABCReader(config, path)
    if name.startswith("hqmx"):
        return CCBReader(config, path)
    return None


def parseUpload(userId, fileBytes, filename):
    """解析上传的账单文件。

    返回 {bankno, suiid, startDate, endDate, details}
    suiid 为空表示该卡号尚未配置账户映射,由前端让用户选择。
    """
    suffix = os.path.splitext(filename)[1] or ".xlsx"
    fd, tmpPath = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(fileBytes)
        config = {"accounts": store.listAccounts(userId)}
        reader = createReader(filename, tmpPath, config)
        if reader is None:
            raise ValueError("无法识别的账单文件: %s(仅支持农行 abc*、建行 hqmx*)" % filename)
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
