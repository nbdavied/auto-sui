import json


def readConfig():
    with open('conf.json') as conf:
        jconf = conf.read()
        conf = json.loads(jconf)
        return conf
