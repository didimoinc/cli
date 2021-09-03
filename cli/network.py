import click
import requests
import hmac
import time
import sys
import platform
from hashlib import sha256

from ._version import __version__


class DidimoAuth(requests.auth.AuthBase):
    def __init__(self, config, path):
        self.config = config
        self.path = path

    def __call__(self, r):
        #uri = self.path
        access_key = self.config.access_key
        #secret_key = self.config.secret_key
        #ts = time.time()
        #nonce = "%fcliclicli" % ts
        #ha1 = sha256(access_key.encode() + secret_key.encode()).hexdigest()
        #ha2 = sha256(access_key.encode() + nonce.encode() + uri.encode()).hexdigest()
        #digest = hmac.new(secret_key.encode(), (ha1 + ha2).encode(), 'sha256').hexdigest()

        r.headers["didimo-api-key"] = access_key

        r.headers["User-Agent"] = "didimo-cli/%s (%s, %s)" % (__version__,
                                                              platform.python_version(),
                                                              platform.system())

        return r


def http_get(url, **kwargs):
    r = requests.get(url, **kwargs)
    if r.status_code == 200:
        return r
    else:
        click.secho('Error %d' % r.status_code, err=True, fg='red')
        click.echo(r.text)
        sys.exit(1)


def http_post(url, **kwargs):
    r = requests.post(url, **kwargs)
    if r.status_code == 200:
        return r
    else:
        click.secho('Error %d' % r.status_code, err=True, fg='red')
        click.echo(r.text)
        sys.exit(1)


def http_post_withphoto(url, access_key, payload, photo):

    files = [('photo', (photo, open(photo, 'rb'), 'image/jpeg'))]

    headers = {
        'DIDIMO-API-KEY': access_key
    }

    r = requests.request("POST", url, headers=headers,
                         data=payload, files=files)

    if r.status_code == 201:
        return r
    else:
        click.secho('Error %d' % r.status_code, err=True, fg='red')
        click.echo(r.text)
        sys.exit(1)
