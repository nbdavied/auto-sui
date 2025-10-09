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
        cardno = soup.find(text='卡号').find_parent('tr').find_all('td')[1].get_text(strip=True)
        dateCycle = soup.find(text='账单周期').find_parent('tr').find_all('td')[1].get_text(strip=True)
        startDate, endDate = dateCycle.split('-')
        startDate = startDate.replace('/','')
        endDate = endDate.replace('/','')
        accountInfo = self.getAccountInfo(cardno)
        suiid = accountInfo['suiid']
        ###
        bankDetails = []
        transGroups = soup.find(text='交易日期').find_parent('div').find_next_siblings('div')
        for transGroup in transGroups:
            detailTrs = transGroup.find_all('table')[1].find_all('tr')
            for tr in detailTrs:
                tds = tr.find_all('td')
                accDate = tds[0].get_text(strip=True)
                accDate = '20' + accDate
                memo = tds[3].get_text(strip=True)
                amtCurr = tds[4].get_text(strip=True)
                amt = amtCurr.split('/')[0]
                transAmt = tds[5].get_text(strip=True)
                transType = 'income'
                if transAmt.startswith('-'):
                    transType = 'payout'
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

        ###
        # detailTrs = soup.find(text='交易日').find_parent('table').find_parent('table').find_parent('table').find_parent(
        #     'table').find_parent('table').find_parent('table').find_parent('table').find_parent('table').findAll('tr', recursive=False)
        
        # for tr in detailTrs[1:]:
        #     columns = tr.find('table').find('table').find(
        #         'table').find('tr').findAll('td', recursive=False)
        #     accDate = columns[1].find('font').text
        #     c4style = columns[4]['style']
        #     memo = columns[4].find('font').text
        #     if c4style == 'width:76px;line-height:normal;':
        #         memo = columns[5].find('font').text
        #     amtCurr = columns[-2].find('font').text
        #     amt = re.findall('(\d+\.*\d*)/', amtCurr)[0]
        #     transAmt = columns[-1].find('font').text
        #     transType = ''
        #     if transAmt[0] == '-':
        #         transType = 'payout'
        #     else:
        #         transType = 'income'
        #     detail = {
        #         'date':accDate,
        #         'time':'080000',
        #         'amount':amt,
        #         'balance':0,
        #         'opAccName':'',
        #         'opAccNo':'',
        #         'transBank':'',
        #         'channel':'',
        #         'transType':transType,
        #         'usage':'',
        #         'memo':memo
        #     }
        #     bankDetails.append(detail)
        return {
            'bankno':cardno,
            'suiid':suiid,
            'startDate':startDate,
            'endDate':endDate,
            'details':bankDetails
        }
