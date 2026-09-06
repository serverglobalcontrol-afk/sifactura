import json
from urllib.parse import urlencode

import requests

from config import settings

AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
USERINFO_URL = 'https://www.googleapis.com/oauth2/v2/userinfo'
DRIVE_API = 'https://www.googleapis.com/drive/v3'
DRIVE_UPLOAD_API = 'https://www.googleapis.com/upload/drive/v3/files'
SCOPE = 'https://www.googleapis.com/auth/drive.file'
REQUEST_TIMEOUT = 20


def is_configured():
    return bool(settings.GOOGLE_DRIVE_CLIENT_ID and settings.GOOGLE_DRIVE_CLIENT_SECRET)


def build_authorization_url(state):
    params = {
        'client_id': settings.GOOGLE_DRIVE_CLIENT_ID,
        'redirect_uri': settings.GOOGLE_DRIVE_REDIRECT_URI,
        'response_type': 'code',
        'scope': SCOPE,
        'access_type': 'offline',
        'prompt': 'consent',
        'state': state,
    }
    return f'{AUTH_URL}?{urlencode(params)}'


def exchange_code_for_tokens(code):
    response = requests.post(TOKEN_URL, data={
        'code': code,
        'client_id': settings.GOOGLE_DRIVE_CLIENT_ID,
        'client_secret': settings.GOOGLE_DRIVE_CLIENT_SECRET,
        'redirect_uri': settings.GOOGLE_DRIVE_REDIRECT_URI,
        'grant_type': 'authorization_code',
    }, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def refresh_access_token(refresh_token):
    response = requests.post(TOKEN_URL, data={
        'refresh_token': refresh_token,
        'client_id': settings.GOOGLE_DRIVE_CLIENT_ID,
        'client_secret': settings.GOOGLE_DRIVE_CLIENT_SECRET,
        'grant_type': 'refresh_token',
    }, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()['access_token']


def get_account_email(access_token):
    response = requests.get(USERINFO_URL, headers={'Authorization': f'Bearer {access_token}'}, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json().get('email')


def get_or_create_folder(access_token, folder_name):
    query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    response = requests.get(
        f'{DRIVE_API}/files',
        headers={'Authorization': f'Bearer {access_token}'},
        params={'q': query, 'fields': 'files(id,name)'},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    files = response.json().get('files', [])
    if files:
        return files[0]['id']
    response = requests.post(
        f'{DRIVE_API}/files',
        headers={'Authorization': f'Bearer {access_token}'},
        json={'name': folder_name, 'mimeType': 'application/vnd.google-apps.folder'},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()['id']


def upload_file(access_token, folder_id, file_path, filename):
    metadata = {'name': filename, 'parents': [folder_id]}
    with open(file_path, 'rb') as f:
        files = {
            'metadata': ('metadata', json.dumps(metadata), 'application/json'),
            'file': (filename, f, 'application/octet-stream'),
        }
        response = requests.post(
            DRIVE_UPLOAD_API,
            headers={'Authorization': f'Bearer {access_token}'},
            params={'uploadType': 'multipart', 'fields': 'id,webViewLink'},
            files=files,
            timeout=300,
        )
    response.raise_for_status()
    return response.json()
