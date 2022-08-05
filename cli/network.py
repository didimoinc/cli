import click
import requests
import hmac
import time
import sys
import platform
from hashlib import sha256

from ._version import __version__

import pickle
import os
import shutil
from datetime import datetime
from ._version import __version__

class DidimoAuth(requests.auth.AuthBase):
    def __init__(self, config, path):
        self.config = config
        self.path = path

    def __call__(self, r):
        access_key = self.config.access_key
        r.headers["didimo-api-key"] = access_key
        r.headers["User-Agent"] = "didimo-cli/%s (%s, %s)" % (__version__,
                                                              platform.python_version(),
                                                              platform.system())
        r.headers["Didimo-Platform"] = "CLI"
        r.headers["Didimo-Platform-Version"] = __version__
        return r


def http_get(url, **kwargs):
    try:
        r = requests.get(url, **kwargs)
        if r.status_code == 200:
            return r
        else:
            click.secho('Error %d' % r.status_code, err=True, fg='red')
            click.echo(r.text)
            sys.exit(1)
    except:
        click.echo("A Network Error Has Occured")
        sys.exit(1)

def http_delete(url, **kwargs):
    try:
        r = requests.delete(url, **kwargs)
        if r.status_code == 204:
            return r
        else:
            click.secho('Error %d' % r.status_code, err=True, fg='red')
            click.echo(r.text)
            #sys.exit(1)
            return r
    except:
        click.echo("A Network Error Has Occured")
        sys.exit(1)

def http_put(url, **kwargs):
    r = requests.put(url, **kwargs)
    if r.status_code == 200:
        return r
    else:
        click.secho('Error %d' % r.status_code, err=True, fg='red')
        click.echo(r.text)
        return r

def http_post(url, **kwargs):
    r = requests.post(url, **kwargs)
    if r.status_code == 200:
        return r
    else:
        click.secho('Error %d' % r.status_code, err=True, fg='red')
        click.echo(r.text)
        sys.exit(1)

def http_post_no_break(url, **kwargs): 
    r = requests.post(url, **kwargs)
    if r.status_code == 200 or r.status_code == 201:
        return r
    else:
        click.secho('Error %d' % r.status_code, err=True, fg='red')
        click.echo(r.text)
        return r

def http_post_withphoto(url, access_key, payload, photo, photo_depth, check_status_code = True):

    if photo_depth != None:
        files = [
            ('photo', (photo, open(photo, 'rb'), 'image/jpeg')),
            ('depth', (photo_depth, open(photo_depth, 'rb'), 'image/png'))
        ]
    else:
        files = [('photo', (photo, open(photo, 'rb'), 'image/jpeg'))]

    headers = {
        'DIDIMO-API-KEY': access_key,
        'Didimo-Platform': "CLI",
        'Didimo-Platform-Version':__version__,
        'User-Agent': "didimo-cli/%s (%s, %s)" % (__version__,
                                                              platform.python_version(),
                                                              platform.system())
    }

    r = requests.request("POST", url, headers=headers,
                         data=payload, files=files)

    if check_status_code:
        if r.status_code == 200 or r.status_code == 201:
            return r
        else:
            click.secho('Error %d' % r.status_code, err=True, fg='red')
            click.echo(r.text)
            #click.echo("An error has occured. Please check your API key")
            sys.exit(1)
    else:
        return r

#cache calls in the same day, and only if the call returns a 200 http status
def cache_this_call(url, access_key, **kwargs):
    curr_date = datetime.today().strftime('%Y-%m-%d')

    root_temp_dir_path = "temp/"
    root_cache_dir_path = root_temp_dir_path+"simple_cache/"
    try:
        directories = [(f.name, f.path)  for f in os.scandir(root_cache_dir_path) if f.is_dir()]
        for (directory_name,directory_path) in directories:
            if not directory_name == curr_date:
                #print("deleting "+directory_name + " at "+directory_path)
                shutil.rmtree(directory_path)
    except OSError as e:
        #print("Error: %s : %s" % (root_cache_dir_path, e.strerror))
        pass

    try: 
        os.mkdir(root_temp_dir_path)
    except OSError as error: 
        pass

    try: 
        os.mkdir(root_cache_dir_path)
    except OSError as error: 
        pass

    try: 
        os.mkdir(root_cache_dir_path+curr_date)
    except OSError as error: 
        pass

    filename = root_cache_dir_path+curr_date+"/"+str(sha256((url+"/"+access_key).encode('utf-8')).hexdigest()) 

    if not os.path.exists(filename):
        #print("no cache")
        data = http_get(url, **kwargs)
        if data.status_code == 200:
            with open(filename, 'wb') as f:
                pickle.dump(data, f)
    else:
        #print("fetching from cache")
        with open(filename, 'rb') as f:
            data = pickle.load(f)
    return data


def clear_network_cache():
    root_cache_dir_path = "temp/simple_cache/"
    try:
        shutil.rmtree(root_cache_dir_path)
    except OSError as e:
        print("Error: %s : %s" % (root_cache_dir_path, e.strerror))

