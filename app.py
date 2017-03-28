#! /usr/bin/env python2
"""Gdrive/Flask/Zappa"""

from ast import literal_eval
from functools import partial
from io import BytesIO
import json
from os import environ as env, remove
from traceback import format_exc
import urlparse
from werkzeug.utils import secure_filename

from flask import Flask, request, jsonify, Response, stream_with_context
import pandas as pd
from pydrive.auth import GoogleAuth, AuthError
from pydrive.drive import GoogleDrive
from pydrive.files import ApiRequestError
from pydrive.settings import InvalidConfigError

#from utils import string_resource_to_json
from middleware import list_routes


app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = '/tmp/uploads'

ALLOWED_EXTENSIONS = dict(
    csv='text/csv',
    doc='application/msword',
    docx='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    json='application/json',
    pdf='application/pdf',
    png='image/png',
    ppt='application/vnd.ms-powerpoint',
    pptx='application/vnd.openxmlformats-officedocument.presentationml.presentation',
    svg='image/svg+xml',
    txt='text/plain',
    xls='application/vnd.ms-excel',
    xlsx='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
)

PANDAS_FILES = dict(
        csv=pd.read_csv,
        xls=pd.read_excel,
        xlsx=pd.read_excel,
        json=pd.read_json,
)

def init_auth():
    """initialize auth when needed"""
    try:
        gauth = GoogleAuth(
            settings_file='settings-%(stage)s.yaml' % dict(stage=env.get('STAGE'))
        )
    except AuthError as err:
        raise(err)
    except InvalidConfigError as err:
        raise(err)
    except Exception as err:
        raise(err)

    try:
        gauth.ServiceAuth()
    except AuthError as err:
        raise(err)
    except InvalidConfigError as err:
        raise(err)

    return GoogleDrive(gauth)


@app.errorhandler(Exception)
def exception_handler(error):
    """Show uncaught exceptions."""
    raise Exception, format_exc()

@app.route('/gdrive')
def list_api_routes():
    """List all endpoints

    Args:
        None

    Returns:
        json list of endpoints.
    """
    return jsonify(list_routes(app))

@app.route('/gdrive/metadata')
def get_file_metadata():
    """Get all metadata on a file or folder.

    Args:
        gdrive url <str>

    Returns:
        json list of lists.
    """
    drive = init_auth()
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

def file_reader(file_extension, **kwargs):
    if file_extension in PANDAS_FILES:
        return partial(PANDAS_FILES[file_extension], **kwargs)
    else:
        return partial(open, mode='rb', buffering=10240)

def yield_dataframe(data):
    """Yield results to fit AWS API Gateway 5MB payload limit."""
    for i in range(0, data.shape[0], 1024):
        yield str(data.iloc[i: i + 1024].to_json(orient='records'))

def yield_bytes(data):
    ONE_MEG
    while True:
        data_bytes = data.read(1024)
        if not data_bytes:
            break
        yield data_bytes

def yield_results(data, mimetype):
    if isinstance(data, pd.DataFrame):
        return Response(yield_dataframe(data), mimetype='application/json')
    else:
        return Response(yield_bytes(data), mimetype=mimetype)

@app.route('/gdrive/read', methods=['GET'])
def read_file():
    """Given a URL or ID of a URL, return the parent folder id and
    file contents as json.

    Args: gdrive url <str>
        **kwargs, any valid kwarg for underlying mimetype for
        pandas read_csv, read_excel, read_json methods.

    Returns:
        json list of dicts for csv, xls[x], json
        OR binary representation of mimetype
    """
    drive = init_auth()
    #kwargs = request.args.to_dict()
    #kwargs.pop('url')
    #kwargs = {str(k): literal_eval(v) for k,v in kwargs.items() if kwargs}

    url = request.args.get('url')
    parsed_id = parse_url(url)
    ifile = drive.CreateFile(dict(id=parsed_id))
    mimetype = ifile['mimeType']
    title = ifile['title']

    tmp_file = '/tmp/{}'.format(title)
    ifile.GetContentFile(tmp_file, mimetype=mimetype)
    file_extension = ifile['fileExtension']

    data = open(tmp_file, 'rb')
    remove(tmp_file)

    return yield_results(data, mimetype)

def create_folder(parent_folder_id, folder_name, drive):
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
        pass
    return folder['id']

def list_folder(folder_id, drive):
    _q = {'q': "'{}' in parents and trashed=false".format(folder_id)}
    file_list =  drive.ListFile(_q).GetList()
    folders = list(filter(
        lambda x: x['mimeType'] == 'application/vnd.google-apps.folder',
        file_list))
    return [{"id": fld["id"], "title": fld["title"]} for fld in folders]

def list_file(folder_id, drive):
    _q = {'q': "'{}' in parents and trashed=false".format(folder_id)}
    file_list =  drive.ListFile(_q).GetList()
    files = list(filter(
        lambda x: x['mimeType'] != 'application/vnd.google-apps.folder',
        file_list))
    return [{"id": fld["id"], "title": fld["title"]} for fld in files]

def validate_file_name(file_name):
    if not file_name:
        raise('no file provided')

    folder, ext = file_name.split('.')[:-1][0], file_name.split('.')[-1]

    if not folder:
        raise('not a valid folder')

    if ext not in ALLOWED_EXTENSIONS:
        raise('%s not a valid file format' % ext)

    return dict(file_name=file_name, folder=folder, ext=ext)

def create_file(folder_id, file_name, data, ext, drive):
    try:
        ifile = drive.CreateFile(dict(
            title=file_name,
            parents=[dict(id=folder_id)],
            mimeType=ALLOWED_EXTENSIONS[ext]))
    except:
        raise("Couldn't create %(file_name)s" % file_name)
    ifile.SetContentString(df.to_csv(index=False))
    ifile.Upload()
    return ifile['alternateLink']

@app.route('/gdrive/write', methods=['POST'])
def write_file():
    """Given file.csv and json data, create file/file.csv.

    Make sure to set your .env for GDRIVE_PARENT_FOLDER_ID.

    Args:

    """
    drive = init_auth()
    args = request.form
    data = secure_filename(request.files['data'])
    file_metadata = validate_file_name(args.get('file_name'))
    folder = file_metadata['folder']
    parent_folder = args.get(
        'folder_id', env.get('GDRIVE_PARENT_FOLDER_ID')
    )

    file_name = file_metadata['file_name']
    ext = file_metadata['ext']
    folder_list = list_folder(parent_folder, drive)
    match = list(filter(lambda x: x['title'] == folder, folder_list))
    folder_id = (
        match[0]['id'] if match else
        create_folder(parent_folder, folder, drive)
    )

    file_list = list_file(folder_id, drive)
    match = list(filter(lambda x: x['title'] == file_name, file_list))

    if match:
        file_id = match[0]['id']
        to_delete = drive.CreateFile({"id": file_id})
        to_delete.Delete()

    url = create_file(
        folder_id=folder_id,
        file_name=file_name,
        data=data,
        ext=ext,
        drive=drive)

    return jsonify(url)

if __name__ == '__main__':
    DEBUG = False if env['STAGE'] == 'prod' else True
    app.run(debug=True, port=5000)
