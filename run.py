import json
import os
from ABCReader import ABCReader
from ABCCreditReader import ABCCreditReader
from BOCCreditReader import BOCCreditReader
from sui import Sui
import gmail
import re
def readConfig():
    with open('conf.json') as conf:
        jconf = conf.read()
        conf = json.loads(jconf)
        return conf
def createBankReader(filename, path):
    if filename[:3] == 'abc':
        return ABCReader(config, os.path.join(path, filename))


def createBankReaderByMail(mail):
    fromEmail = ''
    try:
        fromEmail = re.findall('<(.*)>', mail['From'])[0]
    except IndexError:
        fromEmail = mail['From']
    if fromEmail == 'e-statement@creditcard.abchina.com':
        return ABCCreditReader(config, mail)
    elif fromEmail == 'boczhangdan@bankofchina.com':
        return BOCCreditReader(config, mail)
def determAmount(bankDetail, suiDetail):
    bAmt = bankDetail["amount"]
    sAmt = format(suiDetail["itemAmount"], '0.2f')
    return bAmt == sAmt
def isMatchedDetail(bankDetail, suiDetail, suiid):
    if bankDetail["date"] != suiDetail['sdate']:
        return False
    if not determAmount(bankDetail, suiDetail):
        return False
    transType = bankDetail['transType']
    if transType == 'income':
        if suiDetail['tranType'] == 5:
            return True
        if suiDetail['tranType'] == 2 and str(suiDetail['sellerAcountId']) == suiid:
            return True
    if transType == 'payout':
        if suiDetail['tranType'] == 1:
            return True
        if suiDetail['tranType'] == 2 and str(suiDetail['buyerAcountId']) == suiid:
            return True
    return False

def findSuiDetail(bankDetail, suiDetails, suiid):
    for suiDetail in suiDetails:
        if isMatchedDetail(bankDetail, suiDetail, suiid):
            return suiDetail
    return None
def transDate(date):
    return date[0:4] + '.' + date[4:6] + '.' + date[6:8]
config = None
if __name__ == "__main__":
    config = readConfig()
    f = os.walk(config['detailPath'])
    banks = []
    for path, dirs, files in f:
        for filename in files:
            if filename[:1] == '~':
                continue
            bankReader = createBankReader(filename, path)
            bankDetail = bankReader.analyseData()
            banks.append(bankDetail)
            # print(bankDetail)
    g = gmail.Gmail(config)
    messages = g.getTallyMails()
    for message in messages:
        mail = g.getMail(message['id'])
        bankReader = createBankReaderByMail(mail)
        bankDetail = bankReader.analyseData()
        banks.append(bankDetail)
        
    sui = Sui(config)
    sui.login()
    sui.initTallyInfo()
    for bank in banks:
        suiid = bank['suiid']
        suiDetails = sui.accountDetail(suiid, transDate(bank['startDate']), transDate(bank['endDate']))
        print(suiDetails)
        bankDetails = bank['details']
        # print(bankDetails)
        for bankDetail in bankDetails:
            matchedSuiDetail = findSuiDetail(bankDetail, suiDetails, suiid)
            if matchedSuiDetail != None:
                bankDetail["tranId"] = matchedSuiDetail["tranId"]
                print("------------------------")
                print("已记账条目：")
                print(bankDetail)
                print(matchedSuiDetail)
            else:
                print("------------------------")
                print("未记账条目：")
                print(bankDetail)
                date = bankDetail['date']
                time = bankDetail['time']
                payTime = "%s-%s-%s %s:%s" % (
                    date[0:4], date[4:6], date[6:8], time[0:2], time[2:4])
                if bankDetail['transType'] == 'income':
                    opType = input("请选择记账种类：0-收入 1-转账\r\n")
                    if opType == '0':
                        incomeCate = sui.selectIncomeCategory()
                        sui.income(suiid, bankDetail['amount'], incomeCate['id'], payTime=payTime, memo=bankDetail['memo'])
                    elif opType== '1':
                        opAccount = sui.selectAccount()
                        sui.transfer(opAccount['id'], suiid, bankDetail['amount'], payTime=payTime, memo=bankDetail['memo'])
                else:
                    opType = input("请选择记账种类：1-转账 2-支出\r\n")
                    if opType == '2':
                        payoutCate = sui.selectPayoutCategory()
                        sui.payout(suiid, bankDetail['amount'], payoutCate['id'], payTime=payTime, memo=bankDetail['memo'])
                    elif opType == '1':
                        print("选择转入账户")
                        opAccount = sui.selectAccount()
                        sui.transfer(suiid, opAccount['id'], bankDetail['amount'], payTime=payTime, memo=bankDetail['memo'])
