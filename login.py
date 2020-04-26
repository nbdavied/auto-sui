import requests,json
from hashlib import sha1
from bs4 import BeautifulSoup
import re

HEADERS = {
    'user-agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.108 Safari/537.36'
    }
STATUS = "0"
session = requests.session()
def hex_sha1(s):
    b = bytes(s, encoding="ascii")
    return sha1(b).hexdigest()
def getVCCodeInfo():
    HEADERS['host'] = 'login.sui.com'
    result = session.get("https://login.sui.com/login.do?opt=vccode", headers=HEADERS)
    text = result.text
    return json.loads(text)
def login(username, password, status, uid):
    params = {
        'email':username,
        'status':status,
        'password':password,
        'uid':uid
    }
    HEADERS['host'] = 'login.sui.com'
    result = session.get("https://login.sui.com/login.do", params = params, headers=HEADERS)
    print(result.text)

def authRedirect(method, address, data, count, referer):
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
        result = session.post(address, data=data, headers=header)
    elif method== 'GET' or method == 'get':
        result = session.get(address, params=data, headers=header)
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
    return authRedirect(method, action, data, count + 1, referer)


def getReportIndex():
    params = {
        'm':'a'
    }
    result = session.post('https://www.sui.com/report_index.rmi', params=params)
    print(result.text)
def readConfig():
    with open('conf.json') as conf:
        jconf = conf.read()
        conf = json.loads(jconf)
        return conf
config = readConfig()
#print(config)
username = config['username']
password = config['password']
vccodeInfo = getVCCodeInfo()
password = hex_sha1(password)
password = hex_sha1(username + password)
password = hex_sha1(password + vccodeInfo['vccode'])
#print(password)

login(username, password, STATUS, vccodeInfo['uid'])
#auth = requests.get('https://login.sui.com/auth.do')
authRedirect('get', 'https://login.sui.com/auth.do', {}, 1, "https://login.sui.com")
#getReportIndex()