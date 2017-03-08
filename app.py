#! /usr/bin/env python2
"""Gdrive/Flask/Zappa"""

import json
from os import environ as env
from pprint import pprint as pp
import urlparse

from flask import Flask, request, jsonify
#from odo import odo, discover, resource, dshape
import pandas as pd
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
from pydrive.files import ApiRequestError
from six import StringIO

#from utils import string_resource_to_json
from middleware import list_routes

app = Flask(__name__)

gauth = GoogleAuth(
    settings_file='settings-%(stage)s.yaml' % dict(stage=env.get('STAGE')))
gauth.ServiceAuth()
drive = GoogleDrive(gauth)

def handle_request(method, **kwargs):
    try:
        response = method(**kwargs)
    except requests.exceptions.RequestException as err:
       raise(err)
    return response.json

def get_file_handle(uri):
    uri_id = uri.split('/')[5]
    try:
        ifile = drive.CreateFile({'id': uri_id})
    except ApiRequestError:
        raise(ApiRequestError)

    print(ifile['mimeType'])
    pp(ifile.items())
    return ifile.items()

@app.route('/gdrive')
def list_api_routes():
    """List all endpoints"""
    return jsonify(list_routes(app))

@app.route('/gdrive/metadata')
def get_file_metadata():
    url = request.args.get('url')
    parsed_id = parse_url(url)
    ifile = drive.CreateFile(dict(id=parsed_id))
    print(ifile['mimeType'])
    return jsonify(ifile.items())

def parse_url(url):
    parsed = urlparse.urlparse(url)
    queries = urlparse.parse_qs(parsed.query)
    path = parsed.path.split('/')
    url_id = queries['id'][0] if 'id' in queries else path[3]
    return url_id

@app.route('/gdrive/read', methods=['GET'])
def read_file():
    """Given a URL or ID of a URL, return the parent folder id and
    the csv file contents as json
    https://drive.google.com/open?id=0ByfAQQm9a-DuNEgyXzFoNktCT1k
    """
    url = request.args.get('url')
    parsed_id = parse_url(url)
    ifile = drive.CreateFile(dict(id=parsed_id))
    ifile_contents = StringIO(ifile.GetContentString())
    df = pd.read_csv(ifile_contents)
    folder_id = ifile['parents'][0]['id']
    title = ifile['title']
    return jsonify(
        dict(folder_id=folder_id,
             data=df.to_json(orient='records'),
             file_name=title,
        )
    )

def validate_file_name(file_name, valid_exts=['csv']):
    if not file_name:
        raise('no file provided')

    folder, ext = file_name.split('.')[:-1][0], file_name.split('.')[-1]

    if not folder:
        raise('not a valid folder')

    if ext not in valid_exts:
        raise('Only csv is supported at this time.')

    return dict(file_name=file_name, folder=folder, ext=ext)

def create_folder(parent_folder_id, folder_name):
    try:
        folder = drive.CreateFile(dict(
            title=folder_name,
            parents=[dict(id=parent_folder_id)],
            mimeType="application/vnd.google-apps.folder"
        ))
    except:
        raise('problem creating folder')
    try:
        folder.Upload()
    except:
        raise('failed to upload')
    return folder['id']

def create_file(folder_id, file_name, data):
    try:
        ifile = drive.CreateFile(dict(
            title=file_name,
            parents=[dict(id=folder_id)],
            mimeType='text/csv'))
    except:
        raise("Couldn't create %(file_name)s" % file_name)
    df = pd.DataFrame(data)
    ifile.SetContentString(df.to_csv(index=False))
    ifile.Upload()
    return ifile['alternateLink']

def list_folder(folder_id):
    _q = {'q': "'{}' in parents and trashed=false".format(folder_id)}
    file_list =  drive.ListFile(_q).GetList()
    folders = filter(
        lambda x: x['mimeType'] == 'application/vnd.google-apps.folder',
        file_list)
    return [{"id": fld["id"], "title": fld["title"]} for fld in folders]

def list_file(folder_id):
    _q = {'q': "'{}' in parents and trashed=false".format(folder_id)}
    file_list =  drive.ListFile(_q).GetList()
    files = filter(
        lambda x: x['mimeType'] != 'application/vnd.google-apps.folder',
        file_list)
    return [{"id": fld["id"], "title": fld["title"]} for fld in files]

@app.route('/gdrive/write', methods=['POST'])
def write_file():
    """Given file.csv and json data, create file/file.csv.
    Make sure to set your .env for GDRIVE_PARENT_FOLDER_ID.
    """
    args = request.json
    data = args['data']
    file_name = validate_file_name(args.get('file_name'))
    folder = file_name['folder']
    parent_folder = args.get('folder_id',
                                  env.get('GDRIVE_PARENT_FOLDER_ID'))
    file_name = file_name['file_name']

    folder_list = list_folder(parent_folder)
    match = filter(lambda x: x['title'] == folder, folder_list)
    folder_id = (
        match[0]['id'] if match else
        create_folder(parent_folder, folder)
    )

    file_list = list_file(folder_id)
    match = filter(lambda x: x['title'] == file_name, file_list)
    if not match:
        url = create_file(
            folder_id=folder_id,
            file_name=file_name,
            data=data)
    else:
        file_id = match[0]['id']
        to_delete = drive.CreateFile({"id": file_id})
        to_delete.Delete()
        url = create_file(
            folder_id=folder_id,
            file_name=file_name,
            data=data)
    return jsonify(url)

if __name__ == '__main__':
    DEBUG = False if env['STAGE'] == 'prod' else True
    app.run(debug=True, port=5000)
