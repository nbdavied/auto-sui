from bankReader import BankReader
from bs4 import BeautifulSoup
import re
class ABCCreditReader(BankReader):
    __mail = None
    def __init__(self, config, mail):
        super().__init__(config)
        self.__mail = mail
    
    def analyseData(self):
        data = self.__mail['data']
        soup = BeautifulSoup(data, features="html.parser")
        cardno = soup.find(text='卡号').find_parent(
            'td').next_sibling()[0].find('font').text
        dateCycle = soup.find(text='账单周期').find_parent(
            'td').next_sibling()[0].find('font').text
        startDate = dateCycle[0:8]
        endDate = dateCycle[9:17]
        accountInfo = self.getAccountInfo(cardno)
        suiid = accountInfo['suiid']
        detailTrs = soup.find(text='交易日').find_parent('table').find_parent('table').find_parent('table').find_parent(
            'table').find_parent('table').find_parent('table').find_parent('table').find_parent('table').findAll('tr', recursive=False)
        bankDetails = []
        for tr in detailTrs[1:]:
            columns = tr.find('table').find('table').find(
                'table').find('tr').findAll('td', recursive=False)
            accDate = columns[1].find('font').text
            memo = columns[4].find('font').text
            amtCurr = columns[-2].find('font').text
            amt = re.findall('(\d+\.*\d*)/', amtCurr)[0]
            transAmt = columns[1].find('font').text
            transType = ''
            if transAmt[0] == '-':
                transType = 'payout'
            else:
                transType = 'income'
            detail = {
                'date':accDate,
                'time':'080000',
                'amount':amt,
                'balance':0,
                'opAccName':'',
                'opAccNo':'',
                'transBank':'',
                'channel':'',
                'transType':transType,
                'usage':'',
                'memo':memo
            }
            bankDetails.append(detail)
        return {
            'bankno':cardno,
            'suiid':suiid,
            'startDate':startDate,
            'endDate':endDate,
            'details':bankDetails
        }
