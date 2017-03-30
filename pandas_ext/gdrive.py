"""gdrive handlers for easy read/write to Gdrive"""
from collections import namedtuple
from io import StringIO, BytesIO
from json import loads
from os import environ as env, path, remove

import pandas as pd
import requests

PANDAS_MIMETYPES = {
    'text/csv': pd.read_csv,
    'application/vnd.ms-excel': pd.read_excel,
    'application/vnd.openxmlformats-officedocument.'
    'spreadsheetml.sheet': pd.read_excel,
    'application/json': pd.read_json,
}

PANDAS_EXTENSIONS = dict(
    csv='to_csv',
    xls='to_excel',
    xlsx='to_excel',
    json='to_json',
)


def _get_endpoint_payload():
    """Create route and key headers for gdrive API."""
    endpoint = env['GDRIVE_%s_URL' % env['STAGE'].upper()]
    key = env.get('GDRIVE_%s_KEY' % env['STAGE'].upper())
    headers = {'x-api-key': key} if key else {}
    return dict(headers=headers, route=endpoint)


def read_gdrive(url: str, **kwargs) -> object:
    """Given a url to a csv in gdrive, return namedtuple.

    Args:
        url: gdrive link url
        **kwargs: Passed to read_csv, read_excel, or read_json

    Returns:
        object: Returns dataframe if file mimetype in PANDAS_MIMETYPES
            else file-like object for further processing
    """
    payload = _get_endpoint_payload()
    route = payload['route'] + '/read'
    params = dict(url=url)
    response = requests.get(
        route,
        headers=payload['headers'],
        params=params,
        stream=True,
    )

    mimetype = response.headers['content-type'].split(';')[0]

    return (
        PANDAS_MIMETYPES[mimetype](StringIO(response.text), **kwargs)
        if mimetype in PANDAS_MIMETYPES else
        open(BytesIO(response.raw), 'rb', buffering=1024 * 1024)
    )


def to_gdrive(file_name: str, folder_id: str, data=None, **kwargs) -> str:
    """Send data to gdrive with a given file_name.ext.

    To send any file that doesn't come from a dataframe, make sure to save it
    in /tmp folder. to_gdrive  will know to look there for file_name param.

    Args:
        file_name: Filename.ext stored in /tmp folder.
        folder_id: folder_id associated with meta.folder_id
        data: (:obj:`pd.DataFrame`, optional): Pandas Dataframe, if applicable
            Binary files like PDF or TXT can be sent through to_gdrive with
            data set to None.
        **kwargs: kwargs to pass to to_csv, to_excel, or to_json

    Returns:
        Google Drive alternate web link for preview.
    """
    payload = _get_endpoint_payload()
    route = payload['route'] + '/write'

    ext = file_name.split('.')[-1].lower()
    tmp_file = path.join('/tmp', file_name)

    if (isinstance(data, pd.DataFrame) and
        ext in PANDAS_EXTENSIONS and
        not path.exists(tmp_file)
    ):
        getattr(data, PANDAS_EXTENSIONS[ext])(tmp_file, **kwargs)

    if not path.exists(tmp_file):
        raise('%s not found' % tmp_file)

    file = dict(
        file=(file_name, open(tmp_file, 'rb'))
    )

    data = dict(
        folder_id=folder_id,
    )
    response = requests.post(
        route,
        headers=payload['headers'],
        files=file,
        data=data,
    )
    remove(tmp_file)

    return response.json()


def gdrive_metadata(url: str, fetch_all=False) -> object:
    """Given a gdrive url (file or folder), return all metadata.

    Args:
        url: gdrive link url
        fetch_all: Whether or not to fetch all metadata or not.
            Defaults to False.

    Returns:
        namedtuple if fetch_all is False else dictionary of all metadata
    """
    payload = _get_endpoint_payload()
    route = payload['route'] + '/metadata'
    params = dict(url=url)
    response = requests.get(
        route,
        headers=payload['headers'],
        params=params
    )

    meta_fields = [
        'mimeType',
        'fileExtension',
        'lastModifyingUser',
        'title',
        'parents',
        'fileSize',
        'alternateLink',
    ]

    metadata = {metadata[0]: metadata[1] for metadata in response.json()}
    metadata['folder_id'] = (
        metadata['parents'][0]['id']
        if 'parents' in metadata
        else None
    )
    metadata['last_mod_by_email'] = (
        metadata['lastModifyingUser']['emailAddress']
    )

    if not fetch_all:
        metadata = {
            k: v
            for k, v in metadata.items()
            if k in meta_fields +
            ['folder_id', 'last_mod_by_email']
        }
        del metadata['lastModifyingUser']
        del metadata['parents']
        Metadata = namedtuple('MetaData', metadata.keys())
        return Metadata(**metadata)

    return metadata
