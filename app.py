#! /usr/bin/env python2
"""Gdrive/Flask/Zappa"""

from os import environ as env, remove, path
from traceback import format_exc
import urlparse
from werkzeug.utils import secure_filename

from flask import Flask, request, jsonify, Response
from pydrive.auth import GoogleAuth, AuthError
from pydrive.drive import GoogleDrive
from pydrive.files import ApiRequestError
from pydrive.settings import InvalidConfigError

from middleware import list_routes


app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = '/tmp'

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
    zip='application/zip',
)

ONE_MEGABYTE = 1024 * 1024

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

def parse_url(url):
    parsed = urlparse.urlparse(url)
    queries = urlparse.parse_qs(parsed.query)
    path = parsed.path.split('/')
    url_id = queries['id'][0] if 'id' in queries else path[3]
    return url_id

@app.route('/gdrive/metadata')
def get_file_metadata():
    """Get all metadata on a file or folder.

    Args:
        url <str> # Gdrive url link

    Returns:
        List(List()) # json list of lists.
    """
    drive = init_auth()
    url = request.args.get('url')
    parsed_id = parse_url(url)
    ifile = drive.CreateFile(dict(id=parsed_id))
    print(ifile['mimeType'])
    return jsonify(ifile.items())

def yield_bytes(data):
    while True:
        data_bytes = data.read(ONE_MEGABYTE)
        if not data_bytes:
            break
        yield data_bytes

@app.route('/gdrive/read', methods=['GET'])
def read_file():
    """Given a URL or ID of a URL, return the file.

    Args:
        url <str> # gdrive url link

    Returns:
        fileobject #binary representation of mimetype
    """
    drive = init_auth()
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

    return Response(yield_bytes(data), mimetype=mimetype)

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

    folder, ext = file_name.split('.')[:-1][0], file_name.split('.')[-1].lower()

    if not folder:
        raise('not a valid folder')

    if ext not in ALLOWED_EXTENSIONS:
        raise('%s not a valid file format' % ext)

    return dict(file_name=file_name, folder=folder, ext=ext)

def create_file(folder_id, file_name, ext, drive):
    try:
        ifile = drive.CreateFile(dict(
            title=file_name,
            parents=[dict(id=folder_id)],
            mimeType=ALLOWED_EXTENSIONS[ext]))
    except:
        raise("Couldn't create %s" % file_name)
    ifile.SetContentFile(path.join(app.config['UPLOAD_FOLDER'], file_name))
    ifile.Upload()
    return ifile['alternateLink']

@app.route('/gdrive/write', methods=['POST'])
def write_file():
    """Given file.ext, create file/file.ext.

    Make sure to set your .env for GDRIVE_PARENT_FOLDER_ID.
    This is a folder of last resort if the user doesn't share
    the file or folder with your service account email. It also
    allows you to control who gets access to your files.

    Args:
        data <file-object> # File must exist on your machine
        file_name <str> # Requires extension set
        folder_id <str> # Optional

    Returns:
        str # gdrive alternate link to preview the file.
    """
    drive = init_auth()
    file = request.files['file']
    file_metadata = validate_file_name(file.filename)

    args = request.form
    folder = file_metadata['folder']
    parent_folder_id = args.get(
        'folder_id', env.get('GDRIVE_PARENT_FOLDER_ID')
    )

    file_name = path.join(app.config['UPLOAD_FOLDER'],
                          secure_filename(file_metadata['file_name']))

    file.save(file_name)
    ext = file_metadata['ext']
    folder_list = list_folder(parent_folder_id, drive)
    match = list(filter(lambda x: x['title'] == folder, folder_list))
    folder_id = (
        match[0]['id'] if match else
        create_folder(parent_folder_id, folder, drive)
    )

    file_list = list_file(folder_id, drive)
    match = list(filter(lambda x: x['title'] == file_name, file_list))

    if match:
        file_id = match[0]['id']
        to_delete = drive.CreateFile({"id": file_id})
        to_delete.Delete()

    url = create_file(
        folder_id=folder_id,
        file_name=file_metadata['file_name'],
        ext=ext,
        drive=drive)
    remove(file_name)

    return jsonify(url)

if __name__ == '__main__':
    DEBUG = False if env['STAGE'] == 'prod' else True
    app.run(debug=DEBUG, port=5000)
