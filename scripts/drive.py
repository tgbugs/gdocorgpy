#!/usr/bin/env python3.6
import io
from pathlib import Path
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from httplib2 import Http
from oauth2client import file, client, tools
from pyontutils.config import devconfig
from IPython import embed

spath = Path(devconfig.secrets_file).parent

# derp
# https://developers.google.com/drive/api/v3/integrate-open#open_and_convert_google_docs_in_your_app

def get_oauth_service(readonly=True):
    # https://developers.google.com/drive/api/v3/about-auth
    if readonly:
        store_file = 'google-drive-api-token.json'
        SCOPES = 'https://www.googleapis.com/auth/drive.readonly'
    else:
        store_file = 'google-drive-api-token-rw.json'
        SCOPES = 'https://www.googleapis.com/auth/drive'


    store = file.Storage((spath / store_file).as_posix())
    creds = store.get()
    if not creds or creds.invalid:
        creds_file = devconfig.secrets('google-api-creds-file')
        flow = client.flow_from_clientsecrets((spath / creds_file).as_posix(), SCOPES)
        creds = tools.run_flow(flow, store)
    service = build('drive', 'v3', http=creds.authorize(Http()))
    return service

class Drive:
    def __init__(self, service=None):
        if service is None:
            service = get_oauth_service()

        self.service = service

    def get_doc(self, doc_name, mimeType='text/plain'):
        file_id = devconfig.secrets(doc_name)
        request = self.service.files().export_media(fileId=file_id,
                                                    mimeType=mimeType)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            print("Download %d%%." % int(status.progress() * 100))

        fh.seek(0)
        return fh.read()

if __name__ == '__main__':
    main()
