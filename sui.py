import requests,json
from hashlib import sha1
from bs4 import BeautifulSoup
import re

HEADERS = {
    'user-agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.108 Safari/537.36'
    }
STATUS = "0"

class Sui():
    __config = None
    __session = None
    __incomeCategories = None
    __payoutCategories = None

    def __init__(self, config):
        self.__config = config
        self.__session = requests.session()

    def login(self):
        ### 登陆
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
        print("login result", result.text)
        self.__authRedirect('get', 'https://login.sui.com/auth.do', {}, 1, "https://login.sui.com")
    
    def initTallyInfo(self):
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
        #print(self.__payoutCategories)
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
        print(self.__incomeCategories)


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
        print('第' , count , '次跳转，',method,address, '参数:', data)
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



def readConfig():
    with open('conf.json') as conf:
        jconf = conf.read()
        conf = json.loads(jconf)
        return conf
sui = None
if __name__ == "__main__":
    config = readConfig()
    sui = Sui(config)
    sui.login()
    sui.initTallyInfo()

