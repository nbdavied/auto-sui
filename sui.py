import requests,json
from hashlib import sha1
from bs4 import BeautifulSoup
import re
import time
import json

HEADERS = {
    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
    'user-agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.108 Safari/537.36'
    }
STATUS = "0"

class Sui():
    __config = None
    __session = None
    __incomeCategories = None
    __payoutCategories = None
    __accounts = None

    def __init__(self, config):
        self.__config = config
        self.__session = requests.session()

    def login(self):
        ### 登陆
        print("正在登陆随手记")
        username = self.__config['username']
        password = self.__config['password']
        vccodeInfo = self.__getVCCodeInfo()
        password = self.__hex_sha1(password)
        password = self.__hex_sha1(username + password)
        password = self.__hex_sha1(password + vccodeInfo['vccode'])
        params = {
            'email':username,
            'status':STATUS,
            'password':password,
            'uid':vccodeInfo['uid']
        }
        HEADERS['host'] = 'login.sui.com'
        result = self.__session.get("https://login.sui.com/login.do", params = params, headers=HEADERS)
        # print("login result", result.text)
        self.__authRedirect('get', 'https://login.sui.com/auth.do', {}, 1, "https://login.sui.com")
        print("登陆成功")
    
    def initTallyInfo(self):
        print("选择账本")
        self.__session.get("https://www.sui.com/systemSet/book.do?opt=switch&switchId=1505498391&return=https://www.sui.com/tally/new.do", headers=HEADERS)
        print("初始化收支类型及账户信息")
        result = self.__session.get("https://www.sui.com/tally/new.do", headers=HEADERS)
        soup = BeautifulSoup(result.text, features="html.parser")
        payoutSelect = soup.find(id="levelSelect-payout")
        payoutUl = payoutSelect.find(id="ls-ul1-payout")
        payoutLis = payoutUl.find_all("li", recursive=False)
        self.__payoutCategories = []
        for payoutLi in payoutLis:
            lv1Id = payoutLi["id"][13:]
            lv1Name = payoutLi.find("span")["title"]
            payoutUl2 = payoutLi.find(id="ls-ul2-payout-" + lv1Id)
            payoutLi2s = payoutUl2.find_all("li", recursive=False)[:-1]
            payoutCat = {"id":lv1Id, "name":lv1Name, "subCat":[]}
            self.__payoutCategories.append(payoutCat)
            for payoutLi2 in payoutLi2s:
                lv2id = payoutLi2["id"][13:]
                lv2name = payoutLi2.find("span")["title"]
                lv2Cat = {"id":lv2id, "name":lv2name}
                payoutCat["subCat"].append(lv2Cat)
        print("支出类型", self.__payoutCategories)
        self.__incomeCategories = []
        incomeSelect = soup.find(id="levelSelect-income")
        incomeUl = incomeSelect.find(id="ls-ul1-income")
        incomeLis = incomeUl.find_all("li", recursive=False)
        for incomeLi in incomeLis:
            lv1Id = incomeLi["id"][13:]
            lv1Name = incomeLi.find("span")["title"]
            incomeUl2 = incomeLi.find(id="ls-ul2-income-" + lv1Id)
            incomeLi2s = incomeUl2.find_all("li", recursive=False)[:-1]
            incomeCat = {"id": lv1Id, "name": lv1Name, "subCat": []}
            self.__incomeCategories.append(incomeCat)
            for incomeLi2 in incomeLi2s:
                lv2id = incomeLi2["id"][13:]
                lv2name = incomeLi2.find("span")["title"]
                lv2Cat = {"id": lv2id, "name": lv2name}
                incomeCat["subCat"].append(lv2Cat)
        print("收入类型", self.__incomeCategories)
        accountsUl = soup.find(id="ul_tb-inAccount-5")
        accountLis = accountsUl.find_all('li', recursive=False)
        self.__accounts = []
        for li in accountLis:
            accid = li["id"][17:]
            accName = li.text
            self.__accounts.append({"id":accid, "name":accName})

    def payout(self, account, price, category, id=0, store=0, payTime=None, project=0, member=0, memo='',
                url='', out_account=0, in_account=0, debt_account='', price2=''):
        if payTime == None:
            payTime = time.strftime("%Y-%m-%d %H:%M", time.localtime())
        params = {
            'id':id,
            'category':category,
            'store':store,
            'time': payTime,
            'project':project,
            'member':member,
            'memo':memo,
            'url':url,
            'out_account':out_account,
            'in_account':in_account,
            'debt_account':debt_account,
            'account':account,
            'price':price,
            'price2':price2
        }
        result = self.__session.post(
            'https://www.sui.com/tally/payout.rmi', params=params, headers=HEADERS)
        print("支出记账结果", result.text)

    def income(self, account, price, category, id=0, store=0, payTime=None, project=0, member=0, memo='',
               url='', out_account=0, in_account=0, debt_account='', price2=''):
        if payTime == None:
            payTime = time.strftime("%Y-%m-%d %H:%M", time.localtime())
        params = {
            'id': id,
            'category': category,
            'store': store,
            'time': payTime,
            'project': project,
            'member': member,
            'memo': memo,
            'url': url,
            'out_account': out_account,
            'in_account': in_account,
            'debt_account': debt_account,
            'account': account,
            'price': price,
            'price2': price2
        }
        result = self.__session.post(
            'https://www.sui.com/tally/income.rmi', params=params, headers=HEADERS)
        print('收入记账结果', result.text)

    def transfer(self, out_account, in_account, price, id=0, store=0, payTime=None, project=0, member=0, memo='',
                 url='', debt_account='', account=0, price2=''):
        if payTime == None:
            payTime = time.strftime("%Y-%m-%d %H:%M", time.localtime())
        params = {
            'id': id,
            'store': store,
            'time': payTime,
            'project': project,
            'member': member,
            'memo': memo,
            'url': url,
            'out_account': out_account,
            'in_account': in_account,
            'debt_account': debt_account,
            'account': account,
            'price': price,
            'price2': price2
        }
        result = self.__session.post(
            'https://www.sui.com/tally/transfer.rmi', params=params, headers=HEADERS)
        print('转账记账结果', result.text)

    def accountDetail(self, accountId, beginDate, endDate):
        params = {
            'opt':'list2',
            'beginDate':beginDate,
            'endDate':endDate,
            'cids':0,
            'bids':accountId,
            'sids':0,
            'pids':0,
            'memids': 0,
            'order':'',
            'isDesc': 0,
            'page': 1,
            'note':'',
            'mids': 0
        }
        result = self.__session.post('https://www.sui.com/tally/new.rmi', params=params, headers=HEADERS)
        # print(result.text)
        report = json.loads(result.text)
        details = self.__getDetailInPageData(report)
        pageCount = report['pageCount']
        for i in range(2, pageCount+1):
            params['page'] = i
            result = self.__session.post('https://www.sui.com/tally/new.rmi', params=params, headers=HEADERS)
            report = json.loads(result.text)
            details.extend(self.__getDetailInPageData(report))
        return details
    
    def selectIncomeCategory(self):
        for index, pcat in enumerate(self.__incomeCategories):
            print(index, pcat["name"])
        pcatIndex = int(input('请输入收入类型:'))
        if pcatIndex >= len(self.__incomeCategories):
            return None
        pcat = self.__incomeCategories[pcatIndex]
        for index, scat in enumerate(pcat["subCat"]):
            print(index, scat["name"])
        scatIndex = int(input("请输入收入类型:"))
        if scatIndex >= len(pcat["subCat"]):
            return self.selectIncomeCategory()
        return pcat["subCat"][scatIndex]
    
    def selectPayoutCategory(self):
        for index, pcat in enumerate(self.__payoutCategories):
            print(index, pcat["name"])
        pcatIndex = int(input('请输入支出类型:'))
        if pcatIndex >= len(self.__payoutCategories):
            return None
        pcat = self.__payoutCategories[pcatIndex]
        for index, scat in enumerate(pcat["subCat"]):
            print(index, scat["name"])
        scatIndex = int(input("请输入支出类型:"))
        if scatIndex >= len(pcat["subCat"]):
            return self.selectPayoutCategory()
        return pcat["subCat"][scatIndex]

    def selectAccount(self):
        for index, acc in enumerate(self.__accounts):
            print(index, acc["name"])
        accIndex = int(input("请选择账户:"))
        if accIndex >= len(self.__accounts):
            return None
        return self.__accounts[accIndex]
    
    def printAccounts(self):
        print("随手记账户列表：")
        for acc in self.__accounts:
            print(acc['id'], ':', acc['name'])
    
    def getReportIndex(self):
        params = {
            'm':'a'
        }
        result = self.__session.post('https://www.sui.com/report_index.rmi', params=params)
        print(result.text)
    
    def __hex_sha1(self,s):
        b = bytes(s, encoding="ascii")
        return sha1(b).hexdigest()

    def __getVCCodeInfo(self):
        HEADERS['host'] = 'login.sui.com'
        result = self.__session.get("https://login.sui.com/login.do?opt=vccode", headers=HEADERS)
        text = result.text
        return json.loads(text)

    def __authRedirect(self, method, address, data, count, referer):
        # print('第' , count , '次跳转，',method,address, '参数:', data)
        result = None
        host = re.findall('https://(.*?)/', address)[0]
        header = {
            'user-agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.108 Safari/537.36',
            'Host' :host,
            'Referer':referer,
            'Sec-Fetch-Site':'same-origin',
            'Sec-Fetch-Mode':'navigate',
            'Sec-Fetch-Dest':'document',
            'Upgrade-Insecure-Requests':'1'
        }
        HEADERS['host'] = host
        #print(header)
        if method == 'POST' or method == 'post':
            result = self.__session.post(address, data=data, headers=header)
        elif method== 'GET' or method == 'get':
            result = self.__session.get(address, params=data, headers=header)
        else:
            raise Exception("方法不正确")
        #print(result.text)
        soup = BeautifulSoup(result.text, features="html.parser")
        try:
            onload = soup.find('body')['onload']
            if onload != 'document.forms[0].submit()':
                return
        except:
            return
        action = soup.find('form')['action']
        method = soup.find('form')['method']
        inputs = soup.find('form').find_all('input')
        data = {}
        for input in inputs:
            name = input['name']
            value = input['value']
            data[name] = value
        referer = re.findall('https://.*?/', address)[0]
        if action[0] == '/':
            action = referer + action[1:]
        return self.__authRedirect(method, action, data, count + 1, referer)
    
    def __getDetailInPageData(self, report):
        # print(report)
        details = []
        for group in report['groups']:
            detailList = group['list']
            for detail in detailList:
                dateInfo = detail['date']
                year = 1900 + dateInfo['year']
                month = dateInfo['month'] + 1
                day = dateInfo['date']
                date = '%4d%02d%02d' % (year, month, day)
                detail['sdate'] = date
            details.extend(detailList)
        return details


# if __name__ == "__main__":
    # config = readConfig()
    # sui = Sui(config)
    # sui.login()
    # # sui.initTallyInfo()
    # # sui.income('473619270', 3, '21612954215')
    # # sui.transfer('473619270', '17330926177', 10)
    # details = sui.accountDetail('17330926177', '2020.01.01', '2021.02.01')
    # print(details)
