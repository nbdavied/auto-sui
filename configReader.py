import json


def readConfig():
    with open('conf.json', encoding='utf-8') as conf:
        jconf = conf.read()
        conf = json.loads(jconf)
        return conf
