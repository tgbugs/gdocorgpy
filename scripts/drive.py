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

def get_oauth_service(store_file,
                      creds_file=None,  # if store_file exists don't need this
                      # if creds_file is None it will fail loudly before SCOPES
                      # drop .readonly to get rw
                      # WARNING be sure to also change your store_file name if you do this
                      SCOPES='https://www.googleapis.com/auth/drive.readonly'):
    # https://developers.google.com/drive/api/v3/about-auth

    store = file.Storage((spath / store_file).as_posix())
    creds = store.get()
    if not creds or creds.invalid:
        if creds_file is None:
            etype = 'no creds' if not creds else 'bad creds'
            msg = f'{etype} and store-file not set. Run main to set up.'
            raise FileNotFoundError(msg)
        flow = client.flow_from_clientsecrets((spath / creds_file).as_posix(), SCOPES)
        creds = tools.run_flow(flow, store)
    service = build('drive', 'v3', http=creds.authorize(Http()))
    return service


class Drive:
    def __init__(self, store_file):
        self.service = get_oauth_service(store_file)

    def get_doc(self, doc_name, mimeType='text/plain'):
        file_id = devconfig.secrets('google', 'docs', doc_name)
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

def main():
    # setup
    store_file = devconfig.secrets('google', 'api', 'drive', 'store-file')
    if not Path(store_file).exists():
        SCOPES = 'https://www.googleapis.com/auth/drive.readonly'  # FIXME config this
        creds_file = devconfig.secrets('google', 'api', 'creds-file')
        get_oauth_service(store_file, creds_file, SCOPES)

if __name__ == '__main__':
    main()
