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
        # r'' 必须有:\d 在普通字符串里是非法转义,Python 3.12 起会报 SyntaxError
        bankno = re.findall(r'账号:(\d+)', banknoInfo)[0]
        startDateText = sheet['F2'].value
        startDate = re.findall(r'起始日期:(\d+)', startDateText)[0]
        endDateText = sheet['H2'].value
        endDate = re.findall(r'结束日期:(\d+)', endDateText)[0]
        accountInfo = self.getAccountInfo(bankno)
        # 找到真正的表头行（含“交易日期”列），表头之后才是明细数据。
        # 旧版导出在表头前只有 3 行（标题/账户信息/收支合计），本样例在表头前
        # 多了一行（收支合计），若仍只跳过前 3 行会把表头当数据解析而崩溃。
        rows = list(sheet.rows)
        headerIdx = None
        for i, row in enumerate(rows):
            if row[0].value == '序号' or row[4].value == '交易日期':
                headerIdx = i
                break
        if headerIdx is None:
            # 找不到表头时回退：跳过前 3 行（兼容旧版导出）
            headerIdx = 3
        bankDetails = []
        for row in rows[headerIdx + 1:]:
            date = row[4].value
            if date is None:
                continue  # 跳过空行/汇总行
            time = '080000'
            amount = row[5].value.replace(',','')
            balance = row[6].value
            opAcc = row[8].value
            opAccName = ''
            opAccNo = ''
            if opAcc and '/' in opAcc:
                opAccNo, opAccName = opAcc.split('/', 1)
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
