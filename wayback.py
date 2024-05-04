#!/usr/bin/env python3

from __future__ import annotations
import datetime
import gzip
import json
import logging
import os
import pathlib
import re
import time
import urllib.error
import urllib.request

import cssselect
import lxml.html

logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')

def insert_id_(url: str) -> str:
    _url = url.split('/')
    _url[4] = f'{_url[4]}id_'
    return str.join('/', _url)

def get_url(path: str, url_suffix: str) -> str:
    '''https://archive.org/help/wayback_api.php'''
    closest_timestamp = '20230302'
    url = 'https://archive.org/wayback/available'
    url = f'{url}?timestamp={closest_timestamp}&url=https://wiki.bash-hackers.org/{path}'
    if url_suffix:
        url = f'{url}{url_suffix}'
    response = urllib.request.urlopen(url).read().decode(encoding='utf-8')
    response = json.loads(response).get('archived_snapshots', {}).get('closest', {})
    if response.get('available') and int(response.get('status')) == 200:
        timestamp = datetime.datetime.strptime(response['timestamp'], '%Y%m%d%H%M%S')
        logging.info(f"'{path}' snapshot timestamp: {timestamp}")
        return insert_id_(response.get('url'))

def get_response(url: str) -> str|bytes:
    request = urllib.request.Request(url=url, headers={'user-agent': os.getenv('USERAGENT', 'firefox')})
    try:
        response = urllib.request.urlopen(request)
    except urllib.error.URLError as e:
        return logging.error(e)
    if 'image' in response.info().get('Content-Type'):
        return response.read()
    if response.info().get('Content-Encoding') == 'gzip':
        response = gzip.GzipFile(fileobj=response) # https://pythonhint.com/post/1237769443335170/how-to-decode-the-gzip-compressed-data-returned-in-a-http-response-in-python
    return response.read().decode(encoding='utf-8')

def rename_if_collision(file: pathlib.Path) -> pathlib.Path:
    if file.parent.is_file():
        logging.warning(f'{file.parent} is already a file! renaming to "{file.parent.parent}/_{file.parent.stem}"')
        file = file.parent.rename(file.parent.parent / f'_{file.parent.stem}')
    return file

def write(file:pathlib.Path, response: str|bytes):
    file = rename_if_collision(file=file)
    file.parent.mkdir(exist_ok=True, parents=True)
    if isinstance(response, str):
        file.write_text(response)
    if isinstance(response, bytes):
        file.write_bytes(response)

def export_path(path: str, url_suffix: str = None, file_suffix: str = None):
    url = get_url(path=path, url_suffix=url_suffix)
    if not url:
        return logging.error(f'no url available for "{path}"')
    response = get_response(url=url)
    if not response:
        return logging.error(f'no response for "{url}"')
    if file_suffix == 'md':
        response = MD.get_data(response=response)
    file = pathlib.Path(path)
    if file_suffix:
        file = file.parent / f'{file.name}.{file_suffix}'
    write(file=file, response=response)
    return file


class MD:

    DEAD_LINKS = (
        'commands/builtin/true', 'commands/builtin/source', 'commands/builtin/false', 'commands/builtin/continueBreak', 'commands/builtin/times', 'commands/builtin/command',
        'dict/terms/file', 'dict/terms/hardlink', 'dict/terms/directory',
        'commands/builtin/alias', 'commands/builtin/hash', 'commands/builtin/fc', 'commands/builtin/select', 'commands/builtin/continuebreak'
    )

    def get_data(response: str) -> str:
        response = lxml.html.fromstring(response)
        if response.cssselect('textarea') and response.cssselect('textarea')[0].text:
            assert len(response.cssselect('textarea')) == 1
            return response.cssselect('textarea')[0].text
        return lxml.html.tostring(response).decode('utf-8')

    def get_paths(path: path.Pathlib):
        data = path.read_text()
        internal_link_pattern = re.compile(r'\[\[([:\/\-\w]+)')
        matches = re.findall(pattern=internal_link_pattern, string=data)
        return [match.replace(':', '/') for match in matches if not match.startswith('http')]

    def export():
        unexported = {path: file for file in pathlib.Path('.').rglob('*.md') for path in MD.get_paths(file) if not pathlib.Path(f'{path}.md').exists()}
        if not unexported:
            return logging.warning('no items to export!')
        for path in unexported.keys():
            export_path(path=path, url_suffix='?do=edit', file_suffix='md')
            time.sleep(2)

    def export_all():
        start_file = export_path(path='start', url_suffix='?do=edit', file_suffix='md')
        MD.export()
        MD.export()


class HTML:

    DEAD_LINKS = ('pagead/js/adsbygoogle.js', 'dict/terms/exit_code', 'dict/terms/filename', 'dict/terms/ctime', 'dict/terms/positional_parameter', 'dict/start', 'dict/terms/atime', 'dict/terms/variable', 'dict/terms/shebang', 'dict/terms/return_status')

    def get_paths(path: path.Pathlib):
        data = lxml.html.fromstring(path.read_text())
        href = {urllib.parse.urlparse(element.attrib['href']).path.lstrip('/') for filter in ('a[href]', 'link[href]') for element in data.cssselect(filter) if (element.attrib['href'].startswith('/'))}
        src = {urllib.parse.urlparse(element.attrib['src']).path.lstrip('/') for filter in ('script[src]', 'img[src]') for element in data.cssselect(filter) if (element.attrib['src'].startswith('/'))}
        return href | src

    def export():
        file_paths = sorted(file_path for file_path in pathlib.Path('.').rglob('*') if (file_path.is_file()) and (not file_path.suffix))
        unexported = {path: file for file in file_paths for path in HTML.get_paths(file) if (not pathlib.Path(path).exists()) and (not path.startswith('_export'))}
        logging.info(f'will export the following:\n{list(unexported.keys())}\n')
        for path, source in unexported.items():
            export_path(path=path)
            time.sleep(1)

    def comment_out_menu_tools():
        files = [file for file in sorted(pathlib.Path('.').rglob('*')) if file.is_file() and ('.' not in file.name)]
        for file in files:
            logging.debug(file)
            file_content = file.open(mode='r+').readlines()
            if '<!-- page-tools -->\n' not in file_content:
                continue
            logging.info(f'removing "page-tools" from {file}')
            file_content[file_content.index('<!-- page-tools -->\n')] = '<!-- page-tools\n'
            file_content[file_content.index('<!-- /page-tools -->\n')] = '/page-tools -->\n'
            file.write_text(str.join('', file_content))

    def export_all(self):
        start_file = export_path(path='start')
        pathlib.Path('index.html').symlink_to(start_file)
        _ = [HTML.export() for _ in range(5)]
        self.comment_out_menu_tools()


def main():
    HTML.export_all()
    MD.export_all()
