import json
import os
from ABCReader import ABCReader
from CCBReader import CCBReader
from ABCCreditReader import ABCCreditReader
from BOCCreditReader import BOCCreditReader
from CMBCreditReader import CMBCreditReader
from sui import Sui
import gmail
import re
def readConfig():
    with open('conf.json', encoding='utf-8') as conf:
        jconf = conf.read()
        conf = json.loads(jconf)
        return conf
def saveConfig():
    with open('conf.json', 'w', encoding="utf-8") as conf:
        jsonstr = json.dumps(config, indent=4)
        conf.write(jsonstr)

def createBankReader(filename, path):
    if filename[:3] == 'abc':
        return ABCReader(config, os.path.join(path, filename))
    if filename[:4] == 'hqmx':
        return CCBReader(config, os.path.join(path, filename))


def createBankReaderByMail(mail):
    fromEmail = ''
    try:
        fromEmail = re.findall('<(.*)>', mail['From'])[0]
    except IndexError:
        fromEmail = mail['From']
    if (fromEmail == 'e-statement@creditcard.abchina.com'
        or fromEmail == 'e-statement@creditcard.abchina.com.cn'):
        return ABCCreditReader(config, mail)
    if (fromEmail == 'ccsvc@message.cmbchina.com'):
        return CMBCreditReader(config, mail)

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
    print('时间-date-time：', detail['date'], detail['time'])
    print('金额-amount：', detail['amount'])
    trans = '支出'
    if detail['transType'] == 'income':
        trans = '收入'
    print('交易类型-transType-income/payout：', trans)
    print('对手账号-opAccNo：', detail['opAccNo'])
    print('对手户名-opAccName：', detail['opAccName'])
    print('用途-usage：', detail['usage'])
    print('备注-memo：', detail['memo'])

def saveRule(suiid, op, catid=None, opSuiid=None, memo=None):
    answer = input('是否保存自动记账模板?, y/n ')
    if answer == 'y' or answer == 'Y':
        print("当前记账账号id - ", suiid)
        exp = None
        while True:
            try:
                exp = input('请输入匹配表达式:')
                break
            except:
                pass
        rule = {
            "exp":exp,
            "op":op
        }
        if catid:
            rule['catid'] = catid
        if opSuiid:
            rule['opSuiid'] = opSuiid
        if memo:
            rule['memo'] = memo
        config['rules'].append(rule)
        saveConfig()


def checkExp(exp):
    amount = "1.00"
    transType = "payout"
    opAccNo = ""
    opAccName = ""
    usage = ""
    memo = ""
    bankno = ""
    suiid = ""
    try:
        eval(exp)
    except:
        print('规则表达式存在错误 - ', rule['exp'])
        raise

def checkRulesExp():
    for rule in config["rules"]:
        try:
            checkExp(rule['exp'])
        except:
            raise "表达式配置错误，退出"

def checkRules(detail, bankno, suiid):
    amount = detail['amount']
    transType = detail['transType']
    opAccNo = detail['opAccNo']
    opAccName = detail['opAccName']
    usage = detail['usage']
    memo = detail['memo']
    for rule in config["rules"]:
        try:
            if eval(rule['exp']):
                return rule
        except:
            print('规则表达式错误 - ', rule['exp'])
            pass
    return None

config = None
if __name__ == "__main__":
    config = readConfig()
    checkRulesExp()
    sui = Sui(config)
    sui.login()
    sui.initTallyInfo()
    sui.printAccounts()
    input('随手记数据初始化完成，确认开始读取本地账单')
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
    input('本地账单读取完成')
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
        print(bankDetails)
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
                rule = checkRules(bankDetail, bank['bankno'], suiid)
                if rule != None:
                    print("自动记账 - ", rule['exp'])
                    memo = bankDetail['memo']
                    if 'memo' in rule:
                        memo = rule['memo']
                    if rule['op'] == 'income':
                        print('记账类型 - 收入')
                        sui.income(suiid, bankDetail['amount'], rule['catid'], payTime=payTime, memo=memo)
                    elif rule['op'] == 'payout':
                        print('记账类型 - 支出')
                        sui.payout(suiid, bankDetail['amount'], rule['catid'], payTime=payTime, memo=memo)
                    elif rule['op'] == 'transfer':
                        
                        if bankDetail['transType'] == 'income':
                            # transfer in
                            print('记账类型 - 转入')
                            sui.transfer(rule['opSuiid'], suiid, bankDetail['amount'], payTime=payTime, memo=memo)
                        elif bankDetail['transType'] == 'payout':
                            # transfer out
                            print('记账类型 - 转出')
                            sui.transfer(
                                suiid, rule['opSuiid'], bankDetail['amount'], payTime=payTime, memo=memo)
                    continue

                if bankDetail['transType'] == 'income':
                    opType = input("请选择记账种类：0-收入 1-转账\r\n")
                    if opType == '0':
                        incomeCate = sui.selectIncomeCategory()
                        memo = confirmMemo(bankDetail['memo'])
                        sui.income(suiid, bankDetail['amount'], incomeCate['id'], payTime=payTime, memo=memo)
                        saveRule(suiid, 'income', catid=incomeCate['id'], memo=memo)
                    elif opType== '1':
                        opAccount = sui.selectAccount()
                        memo = confirmMemo(bankDetail['memo'])
                        sui.transfer(opAccount['id'], suiid, bankDetail['amount'], payTime=payTime, memo=memo)
                        saveRule(suiid, 'transfer', opSuiid=opAccount['id'], memo=memo)
                else:
                    opType = input("请选择记账种类：1-转账 2-支出\r\n")
                    if opType == '2':
                        payoutCate = sui.selectPayoutCategory()
                        memo = confirmMemo(bankDetail['memo'])
                        sui.payout(suiid, bankDetail['amount'], payoutCate['id'], payTime=payTime, memo=memo)
                        saveRule(suiid, 'payout', catid=payoutCate['id'], memo=memo)
                    elif opType == '1':
                        print("选择转入账户")
                        opAccount = sui.selectAccount()
                        memo = confirmMemo(bankDetail['memo'])
                        sui.transfer(suiid, opAccount['id'], bankDetail['amount'], payTime=payTime, memo=memo)
                        saveRule(suiid, 'transfer', opSuiid=opAccount['id'], memo=memo)
