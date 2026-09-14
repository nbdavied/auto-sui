from abc import ABCMeta, abstractmethod
import openpyxl

class BankReader(metaclass=ABCMeta):
    __wb = None
    __config = None
    def __init__(self, config):
        self.__config = config

    @abstractmethod
    def analyseData(self):
        pass

    def openExcel(self, filename):
        wb = openpyxl.load_workbook(filename)
        return wb

    def getAccountInfo(self, bankno):
        """按银行卡号找账户配置。

        Web 模式下账户映射由用户在页面上选择,可能尚未保存映射,
        因此这里返回一个空 suiid 的占位而不是 None,避免解析中断。
        """
        for accountInfo in self.__config['accounts']:
            if accountInfo['bankno'] == bankno:
                return accountInfo
        return {"bankno": bankno, "suiid": "", "type": ""}
