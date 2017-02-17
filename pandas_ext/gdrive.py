"""gdrive handlers for easy read/write to Gdrive"""
from collections import namedtuple
from json import loads
from os import environ as env

import pandas as pd
import requests



ENDPOINT = env['GDRIVE_TEST_URL']
KEY = env['GDRIVE_TEST_KEY']
HEADERS = {'x-api-key': KEY}


def read_gdrive(url: str) -> namedtuple:
    """Given a url to a csv in gdrive, return namedtuple."""
    route = ENDPOINT + '/read'
    params = dict(url=url)
    response = requests.get(
        route,
        headers=HEADERS,
        params=params
    )
    results = response.json()
    data = pd.read_json(results['data'])
    folder_id = results['folder_id']

    GdriveFileMetadata = namedtuple(
        'GdriveMetadata',
        ['df', 'folder_id']
    )
    return GdriveFileMetadata(df=data, folder_id=folder_id)

def to_gdrive(file_name: str, data: pd.DataFrame, folder_id: str) -> str:
    """Send data to gdrive with a given file_name.csv.

    You must include folder_id here."""
    route = ENDPOINT + '/write'
    data = dict(
        file_name=file_name,
        folder_id=folder_id,
        data=loads(data.to_json()),
    )
    response = requests.post(
        route,
        headers=HEADERS,
        json=data,
    )

    return response.json()
