from bankReader import BankReader
from bs4 import BeautifulSoup
import re
class CMBCreditReader(BankReader):
    __mail = None
    def __init__(self, config, mail):
        super().__init__(config)
        self.__mail = mail
    
    def analyseData(self):
        accountInfo = self.getAccountInfo("1438")
        suiid = accountInfo['suiid']
        data = self.__mail['data']
        soup = BeautifulSoup(data, features="html.parser")
        band38 = soup.find(id='fixBand38')
        billDateTd  = band38.find('table').find('table').findAll('td')[2]
        billDate = billDateTd.find(id='statementCycle').text
        billDateFrom = billDate.split('-')[0]
        billDateTo = billDate.split('-')[1]
        yearFrom = billDateFrom.split('/')[0]
        yearTo = billDateTo.split('/')[0]
        sameYear = False
        if yearFrom == yearTo:
            sameYear = True
        band39 = soup.find(id='fixBand29')
        table = band39.find('table').find('table').find('table').find('table').find('table')
        trs = table.find('tbody').findAll('tr', recursive=False)
        table2 = trs[1].find('table').find('table')
        band15 = table2.findAll('span', id='fixBand15')
        bankDetails = []
        for span in band15:
            columns = span.find('table').find('table').findAll('td')
            mmdd = columns[2].find('font').text
            accDate = ''
            if sameYear:
                accDate = yearFrom + mmdd
            else:
                if mmdd[:2] == '01':
                    accDate = yearTo + mmdd
                else:
                    accDate = yearFrom + mmdd
            amt = columns[4].find('font').text[2:].replace(',','')
            transType = ''
            if amt[0] == '-':
                transType = 'income'
                amt = amt[1:]
            else:
                transType = 'payout'
            memo = columns[3].find('font').text
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
            'bankno':"1438",
            'suiid':suiid,
            'startDate':billDateFrom.replace('/',''),
            'endDate':billDateTo.replace('/',''),
            'details':bankDetails
        }