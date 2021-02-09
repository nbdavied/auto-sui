from bankReader import BankReader
import re
class ABCReader(BankReader):
    def __init__(self, config, filepath):
        super().__init__(config)
        self.__wb = self.openExcel(filepath)
    def analyseData(self):
        sheet = self.__wb['Sheet1']
        accInfo = sheet['A2'].value
        bankno = re.findall('账号：(\d+)', accInfo)[0]
        startDate = re.findall('起始日期：(\d+)', accInfo)[0]
        endDate = re.findall('截止日期：(\d+)', accInfo)[0]
        accountInfo = self.getAccountInfo(bankno)
        rowIter = sheet.rows
        rowIndex = 0
        bankDetails = []
        for row in rowIter:
            if rowIndex < 3:
                rowIndex = rowIndex + 1
                continue
            date = row[0].value
            time = row[1].value
            amount = row[2].value
            balance = row[3].value
            opAccName = row[4].value
            opAccNo = row[5].value
            transBank = row[6].value
            channel = row[7].value
            usage = row[9].value
            memo = row[10].value
            transType = self.__determTransType(amount)
            amount = amount[1:]
            detail = {
                "date":date,
                "time":time,
                "amount":amount,
                "balance":balance,
                "opAccName":opAccName,
                "opAccNo":opAccNo,
                "transBank":transBank,
                "channel":channel,
                "transType":transType,
                "usage":usage,
                "memo":memo
            }
            bankDetails.append(detail)
        print("导入农业银行账单")
        print("卡号：", bankno)
        return {
            "bankno":bankno,
            "suiid":accountInfo["suiid"],
            "startDate":startDate,
            "endDate":endDate,
            "details":bankDetails
        }

    def __determTransType(self, amount):
        if amount[0] == '+':
            return 'income'
        if amount[0] == '-':
            return 'payout'
        return None
