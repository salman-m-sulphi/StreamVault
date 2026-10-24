"""Owner-authorized YouTube broadcast discovery for StreamVault."""
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import secrets
import time
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen
import webbrowser

SCOPE = 'https://www.googleapis.com/auth/youtube.readonly'
API = 'https://www.googleapis.com/youtube/v3/'


def request_json(url, data=None, headers=None):
    if isinstance(data, dict):
        data = urlencode(data).encode()
    request = Request(url, data=data, headers=headers or {})
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        detail = error.read().decode('utf-8', 'replace')[:1000]
        raise RuntimeError(f'YouTube request failed ({error.code}): {detail}') from error


def read_client(path):
    client = json.loads(Path(path).read_text(encoding='utf-8'))['installed']
    if not client.get('client_id') or not client.get('client_secret'):
        raise ValueError('Choose a Google OAuth Desktop app client JSON file.')
    return client


def authorize(client_path):
    """Use a localhost callback and PKCE; return a refresh token."""
    client = read_client(client_path)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    state = secrets.token_urlsafe(24)
    result = {}

    class Callback(BaseHTTPRequestHandler):
        def do_GET(self):
            params = parse_qs(urlparse(self.path).query)
            if params.get('state', [''])[0] != state:
                result['error'] = 'Sign-in state did not match.'
            elif 'error' in params:
                result['error'] = params['error'][0]
            else:
                result['code'] = params.get('code', [''])[0]
            body = b'StreamVault sign-in received. You may close this tab.'
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(('127.0.0.1', 0), Callback)
    server.timeout = 180
    redirect = f'http://127.0.0.1:{server.server_port}/'
    params = dict(client_id=client['client_id'], redirect_uri=redirect,
                  response_type='code', scope=SCOPE, access_type='offline',
                  prompt='consent', state=state, code_challenge=challenge,
                  code_challenge_method='S256')
    webbrowser.open('https://accounts.google.com/o/oauth2/v2/auth?' + urlencode(params))
    server.handle_request()
    server.server_close()
    if not result.get('code'):
        raise RuntimeError(result.get('error', 'Sign-in timed out.'))
    token = request_json('https://oauth2.googleapis.com/token', dict(
        client_id=client['client_id'], client_secret=client['client_secret'],
        code=result['code'], code_verifier=verifier, redirect_uri=redirect,
        grant_type='authorization_code'))
    if not token.get('refresh_token'):
        raise RuntimeError('Google did not return a refresh token. Reconnect the account.')
    return token['refresh_token']


def access_token(client_path, refresh_token):
    client = read_client(client_path)
    response = request_json('https://oauth2.googleapis.com/token', dict(
        client_id=client['client_id'], client_secret=client['client_secret'],
        refresh_token=refresh_token, grant_type='refresh_token'))
    return response['access_token']


def api_get(token, resource, **params):
    return request_json(API + resource + '?' + urlencode(params),
                        headers={'Authorization': 'Bearer ' + token})


def completed_broadcasts(token, max_pages=3):
    """Newest first; bounded paging keeps routine checks cheap."""
    items = []
    page = None
    for _ in range(max_pages):
        params = dict(part='snippet,status', mine='true', broadcastStatus='completed', maxResults=50)
        if page:
            params['pageToken'] = page
        result = api_get(token, 'liveBroadcasts', **params)
        items.extend(result.get('items', []))
        page = result.get('nextPageToken')
        if not page:
            break
    return sorted(items, key=lambda item: item.get('snippet', {}).get('actualEndTime', ''), reverse=True)


def replay_ready(token, video_id):
    result = api_get(token, 'videos', part='status,processingDetails', id=video_id)
    items = result.get('items', [])
    if not items:
        return False
    video = items[0]
    processing = video.get('processingDetails', {}).get('processingStatus')
    upload = video.get('status', {}).get('uploadStatus')
    return processing == 'succeeded' or (processing is None and upload == 'processed')
