import json
import os
from ABCReader import ABCReader
from sui import Sui
def readConfig():
    with open('conf.json') as conf:
        jconf = conf.read()
        conf = json.loads(jconf)
        return conf
def createBankReader(filename, path):
    if filename[:3] == 'abc':
        return ABCReader(config, os.path.join(path, filename))
    return None
def determTransType(bankDetail):
    if bankDetail["amount"][0] == '+':
        return 'income'
    if bankDetail["amount"][0] == '-':
        return 'payout'
    return None
def determAmount(bankDetail, suiDetail):
    bAmt = bankDetail["amount"][1:]
    sAmt = format(suiDetail["itemAmount"], '0.2f')
    return bAmt == sAmt
def isMatchedDetail(bankDetail, suiDetail, suiid):
    if bankDetail["date"] != suiDetail['sdate']:
        return False
    if not determAmount(bankDetail, suiDetail):
        return False
    transType = determTransType(bankDetail)
    if transType == 'income':
        if suiDetail['tranType'] == 5:
            return True
        if suiDetail['tranType'] == 2 and suiDetail['sellerAcountId'] == suiid:
            return True
    if transType == 'payout':
        if suiDetail['tranType'] == 1:
            return True
        if suiDetail['tranType'] == 2 and suiDetail['buyerAccountId'] == suiid:
            return True
    return False
    
def findSuiDetail(bankDetail, suiDetails, suiid):
    for suiDetail in suiDetails:
        if isMatchedDetail(bankDetail, suiDetail, suiid):
            return suiDetail
    return None

config = None
if __name__ == "__main__":
    config = readConfig()
    g = os.walk(config['detailPath'])
    banks = []
    for path, dirs, files in g:
        for filename in files:
            if filename[:1] == '~':
                continue
            bankReader = createBankReader(filename, path)
            bankDetail = bankReader.analyseData()
            banks.append(bankDetail)
            # print(bankDetail)
    sui = Sui(config)
    sui.login()
    for bank in banks:
        suiid = bank['suiid']
        suiDetails = sui.accountDetail(suiid, "2021.01.02", "2021.02.02")
        print(suiDetails)
        bankDetails = bank['details']
        print(bankDetails)
        for bankDetail in bankDetails:
            transType = determTransType(bankDetail)

