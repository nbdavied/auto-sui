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
    if (fromEmail == 'e-statement@creditcard.abchina.com'
        or fromEmail == 'e-statement@creditcard.abchina.com.cn'):
        return ABCCreditReader(config, mail)

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
def confirmMemo(memo):
    answer = input('是否备注-('+memo+')?,y/n ')
    if answer == 'y' or answer == 'Y' or answer == '':
        return memo
    else:
        nmemo = input('请输入备注 ')
        return nmemo
def printBankDetail(detail):
    print('时间：', detail['date'], detail['time'])
    print('金额：', detail['amount'])
    trans = '支出'
    if detail['transType'] == 'income':
        trans = '收入'
    print('交易类型：', trans)
    print('对手账号：', detail['opAccNo'])
    print('对手户名：', detail['opAccName'])
    print('用途：', detail['usage'])
    print('备注：', detail['memo'])

config = None
if __name__ == "__main__":
    config = readConfig()
    sui = Sui(config)
    sui.login()
    sui.initTallyInfo()
    sui.printAccounts()
    f = os.walk(config['detailPath'])
    banks = []
    for path, dirs, files in f:
        for filename in files:
            if filename[:1] == '~':
                continue
            if filename[-4:] != 'xlsx':
                continue
            bankReader = createBankReader(filename, path)
            bankDetail = bankReader.analyseData()
            banks.append(bankDetail)
            # print(bankDetail)
    if config['gmail']:
        g = gmail.Gmail(config)
        messages = g.getTallyMails()
        for message in messages:
            mail = g.getMail(message['id'])
            bankReader = createBankReaderByMail(mail)
            if bankReader:
                bankDetail = bankReader.analyseData()
                banks.append(bankDetail)
    
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
                printBankDetail(bankDetail)
                date = bankDetail['date']
                time = bankDetail['time']
                payTime = "%s-%s-%s %s:%s" % (
                    date[0:4], date[4:6], date[6:8], time[0:2], time[2:4])
                if bankDetail['transType'] == 'income':
                    opType = input("请选择记账种类：0-收入 1-转账\r\n")
                    if opType == '0':
                        incomeCate = sui.selectIncomeCategory()
                        memo = confirmMemo(bankDetail['memo'])
                        sui.income(suiid, bankDetail['amount'], incomeCate['id'], payTime=payTime, memo=memo)
                    elif opType== '1':
                        opAccount = sui.selectAccount()
                        memo = confirmMemo(bankDetail['memo'])
                        sui.transfer(opAccount['id'], suiid, bankDetail['amount'], payTime=payTime, memo=memo)
                else:
                    opType = input("请选择记账种类：1-转账 2-支出\r\n")
                    if opType == '2':
                        payoutCate = sui.selectPayoutCategory()
                        memo = confirmMemo(bankDetail['memo'])
                        sui.payout(
                            suiid, bankDetail['amount'], payoutCate['id'], payTime=payTime, memo=memo)
                    elif opType == '1':
                        print("选择转入账户")
                        opAccount = sui.selectAccount()
                        memo = confirmMemo(bankDetail['memo'])
                        sui.transfer(
                            suiid, opAccount['id'], bankDetail['amount'], payTime=payTime, memo=memo)
