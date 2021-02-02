from bankReader import BankReader
class ABCReader(BankReader):
    def __init__(self, config, filepath):
        super().__init__(config)
        self.__wb = self.openExcel(filepath)
    def analyseData(self):
        