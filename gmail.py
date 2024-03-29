from __future__ import print_function
import pickle
import os.path
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from httplib2 import socks
import socket
import base64

socket.socket = socks.socksocket
socks.setdefaultproxy(socks.PROXY_TYPE_SOCKS5, '127.0.0.1', 10808)
# If modifying these scopes, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
class Gmail():
    __service = None
    __config = None
    def __init__(self, config):
        print('开始登陆gmail')
        self.__config = config
        self.__initService()
        print('gmail登陆完成')

    def __initService(self):
        creds = None
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', SCOPES)
                creds = flow.run_local_server(port=18566)
            # Save the credentials for the next run
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)

        #http = build_http()
        self.__service = build('gmail', 'v1', credentials=creds)

    def getTallyMails(self):
        results = self.__service.users().messages().list(
            userId='me', labelIds=["Label_20","INBOX"]).execute()
        if 'messages' in results:
            return results['messages']
        else:
            return []

    def getMail(self, id):
        mail = self.__service.users().messages().get(
            userId='me', id=id).execute()
        b64data = self.__getMailContent(mail['payload'])
        html = base64.urlsafe_b64decode(b64data).decode('utf-8')
        headers = mail['payload']['headers']
        headerOb = self.__parseHeaders(headers)

        return {
            'From':headerOb['From'],
            'To':headerOb['To'],
            'Subject':headerOb['Subject'],
            'data':html
        }
    
    def archiveMail(self, id):
        self.__service.users().messages().modify(userId='me', id=id,
                                                 body={"removeLabelIds":['INBOX', 'UNREAD']}).execute()

    def getLabels(self):
        results = self.__service.users().labels().list(userId='me').execute()
        return results
    
    def __parseHeaders(self, headers):
        headerOb = {}
        for h in headers:
            headerOb[h['name']] = h['value']
        return headerOb
    def __getMailContent(self, messagePart):
        mimeType = messagePart['mimeType']
        parts = None
        if mimeType.startswith('multipart'):
            parts = messagePart['parts']
            for part in parts:
                content =  self.__getMailContent(part)
                if content is not None:
                    return content
            return None
        elif mimeType == 'text/html':
            return messagePart['body']['data']
        else:
            return None
    def getService(self):
        return self.__service