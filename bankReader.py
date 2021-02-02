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
