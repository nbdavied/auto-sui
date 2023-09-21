from bankReader import BankReader
import re
class CCBReader(BankReader):
    def __init__(self, config, filepath):
        super().__init__(config)
        self.__wb = self.openExcel(filepath)
    def analyseData(self):
        sheet = self.__wb['Sheet0']
        banknoInfo = sheet['B2'].value
        print(banknoInfo)
        bankno = re.findall('账号:(\d+)', banknoInfo)[0]
        startDateText = sheet['F2'].value
        startDate = re.findall('起始日期:(\d+)', startDateText)[0]
        endDateText = sheet['H2'].value
        endDate = re.findall('结束日期:(\d+)', endDateText)[0]
        accountInfo = self.getAccountInfo(bankno)
        rowIter = sheet.rows
        rowIndex = 0
        bankDetails = []
        for row in rowIter:
            if rowIndex < 3:
                rowIndex = rowIndex + 1
                continue
            date = row[4].value
            time = '080000'
            amount = row[5].value.replace(',','')
            balance = row[6].value
            opAcc = row[8].value
            opAccName = ''
            opAccNo = ''
            if opAcc:
                opAccName = opAcc.split('/')[1]
                opAccNo = opAcc.split('/')[0]
            transBank = ''
            channel = ''
            usage = row[7].value
            memo = row[1].value
            transType = self.__determTransType(amount)
            if transType == 'payout':
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
        print("导入建设银行账单")
        print("卡号：", bankno)
        return {
            "bankno":bankno,
            "suiid":accountInfo["suiid"],
            "startDate":startDate,
            "endDate":endDate,
            "details":bankDetails
        }

    def __determTransType(self, amount):
        if amount[0] == '-':
            return 'payout'
        else:
            return 'income'
