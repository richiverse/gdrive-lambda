#! /usr/bin/env python2
"""Gdrive/Flask/Zappa"""

from os import environ as env, remove, path
from operator import eq, ne
from tempfile import gettempdir
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
app.config['UPLOAD_FOLDER'] = gettempdir()


def allowed_extensions():
    # type: () -> dict
    """Returns extension to mimetype mapping for allowed extensions.

    Args:
        None

    Returns:
        {extension: mimetype}
    """
    return dict(
        csv='text/csv',
        doc='application/msword',
        docx='application/vnd.openxmlformats-officedocument'
            '.wordprocessingml.document',
        json='application/json',
        pdf='application/pdf',
        png='image/png',
        ppt='application/vnd.ms-powerpoint',
        pptx='application/vnd.openxmlformats-officedocument'
            '.presentationml.presentation',
        svg='image/svg+xml',
        txt='text/plain',
        xls='application/vnd.ms-excel',
        xlsx='application/vnd.openxmlformats-officedocument'
            '.spreadsheetml.sheet',
        zip='application/zip',
    )



def init_auth():
    # type: -> GoogleDrive
    """initialize auth when needed

    Args:
        None

    Returns:
        GoogleDrive object
    """
    try:
        gauth = GoogleAuth(
            settings_file=(
                'settings-%(stage)s.yaml' % dict(stage=env.get('STAGE')))
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
    # type: (Exception) -> Exception
    """Show uncaught exceptions.

    Args:
        error

    Raises:
        Exception
        """
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
    # type: (str) -> str
    """Return the 3rd part of the url or get id param if it exists.

    Args:
        url: google drive url

    Returns:
        url id
    """
    parsed = urlparse.urlparse(url)
    queries = urlparse.parse_qs(parsed.query)
    path = parsed.path.split('/')

    return queries['id'][0] if 'id' in queries else path[3]

@app.route('/gdrive/metadata')
def get_file_metadata():
    # type: () -> dict
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
    # type: (file) -> file
    """yield bytes to the caller for the response object.

    There is a hard limit of 5MB of data return so the results are
    streamed to the user.

    Args:
        data is a file object that you want streamed.

    Yields:
        one megabyte of data at a time.
    """
    one_megabyte = 1024 * 1024
    while True:
        data_bytes = data.read(one_megabyte)
        if not data_bytes:
            break
        yield data_bytes


@app.route('/gdrive/read', methods=['GET'])
def read_file():
    # type: () -> file
    """Given a URL or ID of a URL, return the file.

    Args:
        url: # gdrive url link

    Returns:
        fileobject: binary representation of mimetype
    """
    drive = init_auth()
    url = request.args.get('url')
    parsed_id = parse_url(url)
    google_app_mimetypes = {
        'application/vnd.google-apps.document': 'application/vnd'
            '.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.google-apps.presentation': 'application/vnd'
            '.openxmlformats-officedocument.presentationml.presentation',
        'application/vnd.google-apps.spreadsheet': 'application/vnd'
            '.openxmlformats-officedocument.spreadsheetml.sheet',
    }
    ifile = drive.CreateFile(dict(id=parsed_id))
    mimetype = ifile['mimeType']
    title = ifile['title']
    tmp_file = '{}/{}'.format(gettempdir(), title)

    if mimetype in (google_app_mimetypes):
        mimetype = google_app_mimetypes[mimetype]

    ifile.GetContentFile(tmp_file, mimetype=mimetype)
    data = open(tmp_file, 'rb')
    remove(tmp_file)

    return Response(yield_bytes(data), mimetype=mimetype)


def create_folder(parent_folder_id, folder_name, drive):
    # type: (str, str, GoogleDrive) -> str
    """Create a folder at the given folder id location with a folder name.

    Args:
        parent_folder_id: folder location you would like this folder created.
        folder_name: name of the folder.

    Returns:
        folder_id: of this newly created folder.
    """
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
    except ApiRequestError:
        pass

    return folder['id']


def list_file_object(folder_id, directory_only=False, drive):
    # type: (str, GoogleDrive) -> dict
    """List all files in a given folder id.

    Args:
        folder_id: folder id to begin listing.
        drive: Auth object.

    Returns:
        dict(id:file_id, title:file_title)
    """
    _q = {'q': "'{}' in parents and trashed=false".format(folder_id)}
    file_object_list =  drive.ListFile(_q).GetList()
    op = {True: eq, False: ne}[directory_only]
    file_objects = [
        x for x in file_object_list.items()
        if op(x['mimeType'], 'application/vnd.google-apps.folder')
    ]
    return [{"id": fld["id"], "title": fld["title"]} for fld in file_objects]


def validate_file_name(file_name):
    # type: (str) -> dict
    """Validate file name and return file in pieces.

    Args:
        file_name: Full filename + extension.

    Returns:
        dict(file_name: file_name, folder: folder, ext=ext)
    """
    if not file_name:
        raise('no file provided')

    folder, ext = (
        file_name.split('.')[:-1][0],
        file_name.split('.')[-1].lower()
    )

    if not folder:
        raise('not a valid folder')

    if ext not in allowed_extensions():
        raise('%s not a valid file format' % ext)

    return dict(file_name=file_name, folder=folder, ext=ext)


def create_file(folder_id, file_name, ext, to_gapp, drive):
    # type: (str, str, str, bool, GoogleDrive) -> str
    """Creates a file in Google Drive.

    Args:
        folder_id: folder where you want this file created.
        file_name: name of file.
        ext: valid extension in allowed_extensions().
        to_gapp: Convert to google app for csv, xlsx, xls, docx, pptx
        drive: auth object

    Returns:
        Alternate Link to file.
    """
    try:
        ifile = drive.CreateFile(dict(
            title=file_name,
            parents=[dict(id=folder_id)],
            mimetype=allowed_extensions()[ext]))
    except:
        raise("Couldn't create %s" % file_name)

    ifile.SetContentFile(path.join(app.config['UPLOAD_FOLDER'], file_name))
    google_app_extensions = ('csv', 'xls', 'xlsx', 'docx', 'pptx')
    convert_to_google_app = (to_gapp and ext in google_app_extensions)
    ifile.Upload(dict(convert=convert_to_google_app))

    return ifile['alternateLink']


@app.route('/gdrive/write', methods=['POST'])
def write_file():
    # type: () -> str
    """Given file.ext, create file/file.ext.

    Make sure to set your .env for GDRIVE_PARENT_FOLDER_ID.
    This is a folder of last resort if the user doesn't share
    the file or folder with your service account email. It also
    allows you to control who gets access to your files.

    Args:
        file <tuple(file_name:str, file_name:file)>:
            File must exist on your machine.
        folder_id <str>: Optional. Defaults to GDRIVE_PARENT_FOLDER_ID.

    Returns:
        Alternate Link str # gdrive alternate link to preview the file.
    """
    drive = init_auth()
    ifile = request.files['file']
    file_metadata = validate_file_name(ifile.filename)

    args = request.form
    folder = file_metadata['folder']
    parent_folder_id = args.get(
        'folder_id', env.get('GDRIVE_PARENT_FOLDER_ID')
    )
    to_gapp = args.get('to_gapp', False)
    file_name = path.join(app.config['UPLOAD_FOLDER'],
                          secure_filename(file_metadata['file_name']))

    ifile.save(file_name)
    ext = file_metadata['ext']

    folder_list = list_file_object(parent_folder_id, directory_only=True, drive)
    match = [x for x in folder_list.items() if x['title'] == folder]

    folder_id = (
        match[0]['id'] if match else
        create_folder(parent_folder_id, folder, drive)
    )

    file_list = list_file_object(folder_id, drive)
    match = [x for x in file_list.items() if x['title'] == file_name]

    if match:
        file_id = match[0]['id']
        to_delete = drive.CreateFile({"id": file_id})
        to_delete.Delete()

    url = create_file(
        folder_id=folder_id,
        file_name=file_metadata['file_name'],
        ext=ext,
        to_gapp=to_gapp,
        drive=drive
    )
    remove(file_name)

    return jsonify(url)


if __name__ == '__main__':
    DEBUG = False if env['STAGE'] == 'prod' else True
    app.run(debug=DEBUG, port=5000)
