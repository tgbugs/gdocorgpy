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

class UnhandledElementError(Exception):
    """ Don't know what to do with this fellow ... """

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


def get_docs_service(store_file):
    DISCOVERY_DOC = 'https://docs.googleapis.com/$discovery/rest?version=v1'
    store = file.Storage((spath / store_file).as_posix())
    creds = store.get()
    service = build('docs', 'v1', http=creds.authorize(Http()),
                    discoveryServiceUrl=DISCOVERY_DOC)
    return service


class Convert:
    mapping = (
        (('paragraph'),),
        (('paragraph'),),
    )


class OrgDoc:
    def __init__(self, org):
        self.o = org

class DocOrg:
    def __init__(self, docs):
        self.docs = docs

    def json(self, doc_name):
        return self.docs.get_doc_json(doc_name)

    def __call__(self, doc_name, start_heading=''):
        self.j = self.json(doc_name)
        self.start_heading = start_heading
        org = ''
        self.indent = ''
        self.in_table = False
        self.stack = []
        elements = self.j['body']['content']
        org += self.content(self.j['body']['content'])
        self.j = None
        self.start_heading = ''
        return org

    def content(self, content):
        out = ''
        elements = content
        nexts = elements[1:] + [None]
        for element, nxt in zip(elements, nexts):
            e = self.element(element)
            if nxt is not None:
                # peeking to see if we need to strip trailing whitespace
                if 'paragraph' in nxt and nxt['paragraph']['paragraphStyle']['namedStyleType'] != 'NORMAL_TEXT':
                    e = e.rstrip(' ')  # we have a header!

            out += e

        return out

    def element(self, element):
        # start index and end index are probably useful ...
        # esp for crdt type updates
        types = 'table', 'paragraph', 'sectionBreak', 'tableOfContents'
        for t in types:
            if t in element:
                return getattr(self, t)(element[t])
        else:
            print(element.keys())

    def table(self, table):
        sep = '|'
        out = ''
        self.in_table = True
        for row in table['tableRows']:
            for cell in row['tableCells']:
                out += sep + ' '
                for element in cell['content']:
                    content = self.element(element)
                    content = content.replace('\n', '')  # FIXME can newline but hard
                    out += content + ' '

            out += sep + '\n' + self.indent

        self.in_table = False
        return out

    def paragraph(self, paragraph):
        #print(self.stack)
        mapping = {
            'NORMAL_TEXT': '',
            'TITLE': '* ',
            'HEADING_1': '** ',
            'HEADING_2': '*** ',
            'HEADING_3': '**** ',
            'HEADING_4': '***** ',
        }
        out = ''

        style = paragraph['paragraphStyle']['namedStyleType']
        head = mapping[style]
        lh = len(head)
        if lh:
            head = self.start_heading + head
            lh = len(head)
            lsh = len(self.start_heading)
            self.indent = ' ' * lh
            while self.stack and lh <= len(mapping[self.stack[-1]]) + lsh:
                o_head = self.stack.pop(-1)
        
            self.stack.append(style)

            out += head

        if 'bullet' in paragraph:
            bullet = paragraph['bullet']
            listId = bullet['listId']
            lst = self.j['lists'][listId]
            nls = lst['listProperties']['nestingLevels']
            if 'glyphType' in nls[0]:
                symbol = '1. '
            elif 'glyphSymbol' in nls[0]:
                symbol = '- '

            if 'nestingLevel' in bullet:
                nestingLevel = bullet['nestingLevel']
            else:
                nestingLevel = 0

            bhead = (nestingLevel * 2 * ' ')  + symbol
        else:
            bhead = ''

        for element in paragraph['elements']:
            e = self.paragraph_element(element)
            if e.strip():  # issue where bhead appended when last element is empty!?
                e = bhead + e
            out += e

        return out

    def paragraph_element(self, element):
        types = 'textRun', 'inlineObjectElement', 'pageBreak', 'footnoteReference'
        for t in types:
            if t in element:
                return getattr(self, t)(element[t])
        else:
            raise UnhandledElementError(str(element))

    def pageBreak(self, v):
        return '\n'

    def inlineObjectElement(self, ioe):
        oid = ioe['inlineObjectId']
        iobj = self.j['inlineObjects'][oid]
        eobj = iobj['inlineObjectProperties']['embeddedObject']
        types = 'imageProperties', 'embeddedDrawingProperties'
        for t in types:
            if t in eobj:
                obj = eobj[t]
                if obj:
                    uri = obj['contentUri']
                    return f'[[{uri}]]'
                else:
                    return f'>>>Missing embedded object {oid}!<<<'

        else:
            raise TypeError(f'Unknown type in {list(eobj.keys())}')

    def textRun(self, tr):
        ts = tr['textStyle']
        styles = 'underline', 'bold', 'italic', 'strikethrough'
        lt = '' if self.in_table else '\n' + self.indent
        mapping = {
            'underline': '_',
            'bold': '*',
            'italic': '/',
            'strikethrough': '+',  # TODO haven't seen this yet
            'line-terminator': lt,
            'trailing-whitespace': ' ',
        }
        stack = []
        out = ''  # FIXME reverse whitespace ...

        content = tr['content']
        content = self.textRun_content_normalize(content, lt)

        # don't style trailing whitespace
        # it is too hard to fix this stuff in the wysiwyg so just fix it here
        while content.endswith(' '):
            stack.append('trailing-whitespace')
            content = content[:-1]

        while content.endswith('\n'):
            stack.append('line-terminator')
            content = content[:-1]

        # don't style leading whitespace
        # it is too hard to fix this stuff in the wysiwyg so just fix it here
        while content.startswith(' '):
            out += ' '
            content = content[1:]

        if content:  # only style if there is content
            for style in styles:
                if style in ts:
                    if style == 'underline' and 'link' in ts:
                        style = 'link'
                        href = ts['link']['url']
                        mapping['link'] = f'[[{href}]['

                    out += mapping[style]
                    stack.append(style)

            out += content

        while stack:
            style = stack.pop(-1)
            if style == 'link':
                out += ']]'
            else:
                out += mapping[style]

        return out

    @staticmethod
    def textRun_content_normalize(content, lt):
        vertical_tab = '\x0b'  # apparently C-<enter> in docs produces this madness
        return content.replace(vertical_tab, lt)

    def footnoteReference(self, value):
        footnoteId = value['footnoteId']
        fobj = self.j['footnotes'][footnoteId]
        out = '[fn::'
        fn = self.content(fobj['content'])
        out += fn.strip()  # FIXME pass a skip leading whitespace argument?
        out += ']'
        return out
       
    def sectionBreak(self, value):
        return '\n'

    def tableOfContents(self, value):
        return ''


class Docs:
    def __init__(self, store_file, converter=DocOrg):
        self.service = get_docs_service(store_file)
        self.converter = converter(self)

    def get_doc_json(self, doc_name):
        file_id = devconfig.secrets('google', 'docs', doc_name)
        return self.service.documents().get(documentId=file_id,
                                            suggestionsViewMode='SUGGESTIONS_INLINE').execute()

    def get_doc_org(self, doc_name, start_heading='**'):
        return self.converter(doc_name, start_heading=start_heading)

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
