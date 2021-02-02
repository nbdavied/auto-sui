from abc import ABCMeta, abstractmethod
import openpyxl

class BankReader(metaclass=ABCMeta):
    config = None
    def __init__(self, config):
        self.config = config
    
    @abstractmethod
    def read(self):
        pass