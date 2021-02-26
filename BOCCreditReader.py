from bankReader import BankReader
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta
from monthdelta import monthdelta
class BOCCreditReader(BankReader):
    __mail = None

    def __init__(self, config, mail):
        super().__init__(config)
        self.__mail = mail

    def analyseData(self):
        data = self.__mail['data']
        soup = BeautifulSoup(data, features="html.parser")
        cardno = soup.find_all(class_='card')[1].text.strip()
        sTallyDate = soup.find(class_='bill_sum_detail_table').find(
            'tbody').find_all('td')[1].text
        tallyDate = datetime.strptime(sTallyDate, '%Y-%m-%d')
        startDate = tallyDate - monthdelta(1) + timedelta(days=1)
        startDate = startDate.strftime('%Y%m%d')
        endDate = tallyDate.strftime('%Y%m%d')
        accountInfo = self.getAccountInfo(cardno)
        suiid = accountInfo['suiid']
        rmbBillTable = soup.find_all(class_='bill_pay_des')[1]
        trs = rmbBillTable.find('tbody').find_all('tr')
        bankDetails = []
        for tr in trs:
            tds = tr.find_all('td')
            accDate = tds[1].text.strip().replace('-','')
            memo = tds[3].text.strip()
            amt = tr.find(class_='money_show_sign').text.strip()
            transType = ''
            if tds[5].text.strip() == amt:
                transType = 'payout'
            else:
                transType = 'income'
            detail = {
                'date': accDate,
                'time': '080000',
                'amount': amt,
                'balance': 0,
                'opAccName': '',
                'opAccNo': '',
                'transBank': '',
                'channel': '',
                'transType': transType,
                'usage': '',
                'memo': memo
            }
            bankDetails.append(detail)
        return {
            'bankno': cardno,
            'suiid': suiid,
            'startDate': startDate,
            'endDate': endDate,
            'details': bankDetails
        }
