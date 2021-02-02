import json
import os
from ABCReader import ABCReader
def readConfig():
    with open('conf.json') as conf:
        jconf = conf.read()
        conf = json.loads(jconf)
        return conf
def createBankReader(filename, path):
    if filename[:3] == 'abc':
        return ABCReader(config, os.path.join(path, filename))
    return None

config = None
if __name__ == "__main__":
    config = readConfig()
    g = os.walk(config['detailPath'])
    for path, dirs, files in g:
        for filename in files:
            bankReader = createBankReader(filename, path)
            bankDetail = bankReader.analyseData()

