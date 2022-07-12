import click
import sys
import time
import multiprocessing

from .network import DidimoAuth, http_get
from urllib import parse as urlparse


class URL(click.ParamType):
    name = "url"

    def convert(self, value, param, ctx):
        if not isinstance(value, tuple):
            value_parsed = urlparse.urlparse(value)
            if value_parsed.scheme not in ("http", "https"):
                self.fail("invalid URL scheme", param, ctx)
            if value_parsed.netloc == "":
                self.fail("host is empty", param, ctx)
        return value


def get_didimo_status(config, id):
    api_path = "/v3/didimos/" + id
    url = config.api_host + api_path
    r = http_get(url, auth=DidimoAuth(config, api_path))
    return r.json()

def get_asset_status(config, id):
    api_path = "/v3/assets/" + id
    url = config.api_host + api_path
    r = http_get(url, auth=DidimoAuth(config, api_path))
    return r.json()

#Polls the API for progress update until the didimo generation pipeline is finished. Returns 0 if the process is successfull or return 1 if there is an error. 
def wait_for_dgp_completion(config, key, timeout):

    manager = multiprocessing.Manager()
    return_dict = manager.dict()

    if timeout is not None:
        # Start foo as a process
        p = multiprocessing.Process(target=wait_for_dgp_completion_aux, name="Wait_for_dgp_completion_aux", args=(config,key,return_dict))
        p.start()

        # Wait 10 seconds for foo
        p.join(float(timeout))

        # If thread is active
        if p.is_alive():
            click.secho("Timeout!")

            # Terminate foo
            p.terminate()

            # Cleanup
            p.join()

            return 3 #return timeout error
        else:
            return return_dict[0] #return function result
    else:
        wait_for_dgp_completion_aux(config, key, return_dict)
        return return_dict[0]


def wait_for_dgp_completion_aux(config, key, return_dict):

    last_status = ""
    while True:
        response = get_asset_status(config, key) 
        percent = response.get('percent', 100)
        status = response.get('status', '')

        if status != last_status:
            last_status = status
            click.secho("Status: "+str(status))

        if status == "processing":
            click.secho("Progress: "+str(percent))

        if response['status_message'] != "":
            click.secho(err=True)
            click.secho('Error: %s' %
                        response["status_message"], err=True, fg='red')
            return_dict[0] = 1
            return
        if response['status'] == 'done':
            return_dict[0] = 0
            return
        time.sleep(10)
    click.secho("This statement should never be reached...")
    return_dict[0] = 3
    return

def download_didimo(config, id, package_type, output_path, showProgressBar=True):
    api_path = "/v3/didimos/" + id
    url = config.api_host + api_path
    r = http_get(url, auth=DidimoAuth(config, api_path))

    for package_itm in r.json()['transfer_formats']:
        s3url = ""
        
        output_filename = id+"_"+package_itm["name"] + ".zip"
        output_path_full = output_path+output_filename

        if package_type == None or len(package_type) == 0:
            s3url = package_itm["__links"]["self"]
        else:
            if package_itm["name"] == package_type:
                s3url = package_itm["__links"]["self"]

        if s3url != "":
            #print ("downloading.... "+s3url)
            try: 
                with http_get(s3url, auth=DidimoAuth(config, api_path)) as r:
                    r.raise_for_status()
                    zipsize = int(r.headers.get('content-length', 0))
                    with click.open_file(output_path_full, 'wb') as f:
                        if showProgressBar:
                            label = "Downloading %s" % id
                            with click.progressbar(length=zipsize, label=label) as bar:
                                for chunk in r.iter_content(chunk_size=2048):
                                    size = f.write(chunk)
                                    bar.update(size)
                        else:
                            for chunk in r.iter_content(chunk_size=zipsize):
                                size = f.write(chunk)
                if showProgressBar:
                    click.secho('Downloaded to %s' % output_filename, fg='blue', err=True)
            except Exception as error: 
                click.secho('Error downloading to %s: %s' % (output_filename, error), fg='red', err=True)
                #pass
            

        # else:
            # print ("Unable to download")


def download_asset(config, asset_url, api_path, output_path):

    if asset_url != "":
        print ("downloading....")
        with http_get(asset_url, auth=DidimoAuth(config, api_path)) as r:
            r.raise_for_status()
            zipsize = int(r.headers.get('content-length', 0))
            with click.open_file(output_path, 'wb') as f:
                label = "Downloading %s" % id
                with click.progressbar(length=zipsize, label=label) as bar:
                    for chunk in r.iter_content(chunk_size=2048):
                        size = f.write(chunk)
                        bar.update(size)
        click.secho('Downloaded to %s' % output_path, fg='blue', err=True)

    else:
        print ("Unable to download")
