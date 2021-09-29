import click
import sys

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


def download_didimo(config, id, package_type, output_path):

    api_path = "/v3/didimos/" + id
    url = config.api_host + api_path
    r = http_get(url, auth=DidimoAuth(config, api_path))
    s3url = ""

    for package_itm in r.json()['transfer_formats']:

        if package_type == None or len(package_type) == 0:
            s3url = package_itm["__links"]["self"]
        else:
            if package_itm["name"] == package_type:
                s3url = package_itm["__links"]["self"]

        if s3url != "":
            print ("downloading....")
            with http_get(s3url, auth=DidimoAuth(config, api_path)) as r:
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
