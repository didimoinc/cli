import click
import json
import sys
import time
import requests

from .utils import print_key_value, print_status_header, print_status_row
from .network import DidimoAuth, http_get, http_post, http_post_withphoto
from .config import Config
from .helpers import get_didimo_status, download_didimo, URL, download_asset
from ._version import __version__

pass_api = click.make_pass_decorator(Config)

CONTEXT_SETTINGS = dict(help_option_names=['--help', '-h'])


@click.group(context_settings=CONTEXT_SETTINGS)
@click.option("-c", "--config", help="Use this configuration instead of the default one.")
@click.pass_context
def cli(ctx, config):
    """
    Create, list and download didimos
    """
    ctx.ensure_object(Config)
    if ctx.invoked_subcommand not in ["init", "version"]:
        ctx.obj.load()
        if config != None:
            ctx.obj.load_configuration(config)
        else:
            ctx.obj.load_configuration(ctx.obj.configuration)


@cli.command(short_help="Initializes configuration")
@click.argument("name", required=True)
@click.option('--host', type=URL(), prompt=True, help="API host with protocol.", default="https://api.didimo.co", show_default=True)
@click.option('--api-key', prompt="API Key", help="API Key from your credentials.")
@click.option('--api-secret', prompt="API Secret", help="API Secret from your credentials.")
@pass_api
def init(config, name, host, api_key, api_secret):
    """
    Initializes configuration

    <NAME> is the name of the configuration that will be added.
    """
    config.init(name, host, api_key, api_secret)


@cli.command()
@click.option("-n", "--number", required=False, default=1, show_default=True,
              help="Number of pages to query from the API. Each page has 10 didimos.")
@click.option("-r", "--raw", required=False, is_flag=True, default=False,
              help="Do not format output, print raw JSON response from API, ignoring --number.")
@pass_api
def list(config, number, raw):
    """
    List didimos
    """
    api_path = "/v3/didimos/"
    url = config.api_host + api_path
    r = http_get(url, auth=DidimoAuth(config, api_path))
    if raw:
        click.echo(r.text)
    else:

        if number < 1:
            sys.exit(0)

        didimos = []
        page = 1
        didimos += r.json()['didimos']

        while page != number:

            next_page = r.json()['__links']['next']
            if next_page != None:
                api_path = next_page
                url = api_path
                r = http_get(url, auth=DidimoAuth(config, api_path))
                didimos += r.json()['didimos']
                page += 1
            else:
                break

        print_status_header()
        for didimo in didimos:
            print_status_row(didimo)


@cli.command()
@click.option("-r", "--raw", required=False, is_flag=True, default=False,
              help="Do not format output, print raw JSON response from API.")
@pass_api
def account(config, raw):
    """
    Get account information
    """
    api_path = "/v3/accounts/default/status"
    url = config.api_host + api_path

    r = http_get(url, auth=DidimoAuth(config, api_path))
    response = r.json()

    if raw:
        click.echo(r.text)
    else:

        #tier = response["tier"]["name"]
        #print (response["owner_profile_uuid"])
        #print (tier)

        api_path2 = "/v3/didimos/"
        url2 = config.api_host + api_path2

        #print (url2)

        r2 = http_get(url2, auth=DidimoAuth(config, api_path2))
        didimos = r2.json()

        print_key_value("Tier", response["tier"]["name"])
        print_key_value("Points", response["balance"])
        print_key_value("Total didimos in account", didimos['total_size'])
        expiry_message = "\n(!) %s points will expire at %s" % \
            (response["next_expiration_points"],
             response["next_expiration_date"])
        click.secho(expiry_message, fg="yellow", err=True)


@cli.command(short_help="Create a didimo")
@click.argument("type", type=click.Choice(["photo"]), required=True, metavar="TYPE")
@click.argument("input", type=click.Path(exists=True), required=True)
@click.option('--depth', '-d',
              type=click.Path(), required=False,
              help="Create didimo with depth")
@click.option('--feature', '-f', multiple=True,
              type=click.Choice(
                  ["oculus_lipsync", "simple_poses", "arkit", "aws_polly"]),
              help="Create didimo with optional features. This flag can be used multiple times.")
@click.option('--max-texture', '-m', multiple=False,
              type=click.Choice(
                  ["512", "1024", "2048"]),
              help="Create didimo with optional max texture dimension. ")
@click.option('--no-download', '-n', is_flag=True, default=False,
              help="Do not download didimo")
@click.option('--no-wait', '-w', is_flag=True, default=False,
              help="Do not wait for didimo creation and do not download")
@click.option("--output", "-o", type=click.Path(), required=False,
              help="Path to download the didimo. If multiple package types "
              "are present or if the flags --no-wait or --no-download "
              "are present, this option is ignored. [default: <ID>.zip]")
@click.option('--package-type', '-p', multiple=True,
              type=click.Choice(["fbx", "gltf"]),
              help="Specify output types for this didimo. This flag can be used multiple times.", show_default=True)
@click.option("--version", "-v",
              type=click.Choice(["2.5"]),
              default="2.5",
              help="Version of the didimo.", show_default=True)
@pass_api
def new(config, type, input, depth, feature, max_texture, no_download, no_wait, output, package_type, version):
    """
    Create a didimo

    TYPE is the type of input used to create the didimo. Accepted values are:

    \b
        - photo (input must be a .jpg/.jpeg/.png)
        - depth (input must be a .png)

        For more information on the input types, visit
        https://docs.didimo.co/api/?javascript#new\b

    INPUT is the path to the input file.

    \b
    Examples:
        Create a didimo from a photo
        $ didimo new photo /path/input.jpg

    """

    api_path = "/v3/didimos"
    url = config.api_host + api_path

    payload = {
        'input_type': 'photo'
    }

    if depth != None:
        payload["input_type"] = "rgbd"
    else:
        payload["input_type"] = "photo"

    if len(package_type) > 0:
        payload["transfer_formats"] = package_type
        package_type = package_type[0]
    else:
        package_type = "gltf"

    if max_texture != None:
        payload["max_texture_dimension"] = max_texture

    for feature_item in feature:
        payload[feature_item] = 'true'

    r = http_post_withphoto(url, config.access_key, payload, input, depth)

    didimo_id = r.json()['key']

    click.echo(didimo_id)
    if not no_wait:
        with click.progressbar(length=100, label='Creating didimo') as bar:
            last_value = 0
            while True:
                response = get_didimo_status(config, didimo_id)
                percent = response.get('percent', 100)
                update = percent - last_value
                last_value = percent
                bar.update(update)
                if response['status_message'] != "":
                    click.secho(err=True)
                    click.secho('Error: %s' %
                                response["status_message"], err=True, fg='red')
                    sys.exit(1)
                if response['status'] == 'done':
                    break
                time.sleep(2)
        if not no_download:
            if output == None:
                output = "%s_%s.zip" % (didimo_id, package_type)
            download_didimo(config, didimo_id, "", output)


@cli.command(short_help='Get status of didimos')
@click.argument("id", required=True, nargs=-1)
@click.option("-r", "--raw", required=False, is_flag=True, default=False,
              help="Do not format output, print raw JSON response from API.")
@click.option("-s", "--silent", required=False, is_flag=True, default=False,
              help="Do not print anything. See help text for exit codes.")
@pass_api
def status(config, id, raw, silent):
    """
    Get status of didimos

    <ID> is the didimo ID to get information.

    Multiple didimo IDs are accepted, separated by a space or newline

    If <ID> is the character "-", read the IDs from STDIN.

    When using the --silent flag, the following exit code rules are applied:

    \b
      - 0: Every didimo is in "Done" state
      - 1: At least one didimo is in "Error" state
      - 2: At least one didimo is in "Pending" or "Processing" state
    """
    didimos = []

    ids = set(id)

    # read didimo ids if used with a pipe
    if "-" in ids:
        ids = sys.stdin.readlines()

    for didimo in ids:

        response = get_didimo_status(config, didimo.rstrip())

        # TODO
        # Remove this block when /status endpoint is consistent with /list
        if response['status_message'] != "":
            response["key"] = didimo.rstrip()
            response["status"] = "error"

        didimos.append(response)
        if silent:
            if response["status"] == "error":
                click.echo("Error on \"%s\"" % response["key"], err=True)
                sys.exit(1)
            if response["status"] in ["pending", "processing"]:
                sys.exit(2)

    if silent:
        sys.exit(0)

    if raw:
        click.echo(json.dumps(didimos, indent=4))
    else:
        print_status_header()
        for didimo in didimos:
            print_status_row(didimo)


@cli.command(short_help="Get or set configuration")
@click.argument("name", required=False)
@pass_api
def config(config, name):
    """
    Get or set configuration

    With no arguments, list all available configurations.

    If <NAME> is provided, set that as the default configuration.
    """
    if name == None:
        config.list_configurations()
    else:
        click.echo("Setting default configuration to \"%s\"" % name, err=True)
        config.save_configuration(name)
        click.secho("Configuration file saved.", fg='blue', err=True)


@cli.command()
@click.argument("id", required=True)
@click.option("-o", "--output", type=click.Path(),
              help="Download path. [default: <ID>.zip]")
@click.option('--package-type', '-p',
              type=click.Choice(["fbx", "gltf"]),
              help="Specify output type for this didimo.", show_default=True)
@pass_api
def download(config, id, output, package_type):
    """
    Download a didimo

    <ID> is the didimo ID.

    When given the "-" character, read the didimo
    ID from STDIN.
    """

    if id == "-":
        id = sys.stdin.readlines()[0].rstrip()

    if output is None:
        output = "%s_%s.zip" % (id, package_type)
    download_didimo(config, id, package_type, output)


@cli.command()
@pass_api
def version(config):
    """
    Print version and exit
    """
    print(__version__)
    sys.exit(0)


@cli.group()
@pass_api
def execute(config):
    """
    Execute on-demand features on didimos
    """
    pass


@execute.command(short_help="Produce high fidelity hairs on a didimo")
@click.argument("input", type=click.Path(exists=True), required=True)
@pass_api
def hairsdeform(config, input):
    """
    Produce high fidelity hairsdeform on a didimo

    <INPUT> is your deformation file.

    Returns the didimo asset ID that you can use with other commands and hairsdeform package.
    """

    api_path = "/v3/assets"
    url = config.api_host + api_path

    payload = {
        'input_type': 'hairs_deform'
    }

    files = [('template_deformation', (input, open(
        input, 'rb'), 'application/octet-stream'))]

    headers = {
        'DIDIMO-API-KEY': config.access_key
    }

    r = requests.request("POST", url, headers=headers,
                         data=payload, files=files)

    if r.status_code != 201:
        click.secho('Error %d' % r.status_code, err=True, fg='red')
        click.echo(r.text)
        sys.exit(1)

    response = r.json()

    key = response['key']
    url = ""
    for package_itm in r.json()['transfer_formats']:
        url = package_itm["__links"]["self"]
        break

    click.echo(response['key'])
    output = "%s.zip" % key

    click.echo("Creating package file.")
    time.sleep(15)
    download_asset(config, url, api_path, output)


@execute.command(short_help="Deform a model to match a didimo shape")
@click.argument("vertex", required=True, type=click.Path(exists=True))
@click.argument("user_asset", required=True, type=click.Path(exists=True))
@pass_api
def vertexdeform(config, vertex, user_asset):
    """
    Deform a model to match a didimo shape

    <VERTEX> is your vertex file.
    <USER_ASSET> is your asset file.

    Returns an asset ID of the deformed vertex that you can use with other commands and the package.
    """

    api_path = "/v3/assets"
    url = config.api_host + api_path

    payload = {'input_type': 'vertex_deform'}

    files = [
        ('template_deformation', (vertex, open(
            vertex, 'rb'), 'application/octet-stream')),
        ('user_asset', (user_asset, open(user_asset, 'rb'), 'application/octet-stream'))
    ]

    headers = {
        'DIDIMO-API-KEY': config.access_key
    }

    r = requests.request("POST", url, headers=headers,
                         data=payload, files=files)

    if r.status_code != 201:
        click.secho('Error %d' % r.status_code, err=True, fg='red')
        click.echo(r.text)
        sys.exit(1)

    response = r.json()

    key = response['key']
    url = ""
    for package_itm in r.json()['transfer_formats']:
        url = package_itm["__links"]["self"]
        break

    click.echo(response['key'])
    output = "%s.zip" % key

    click.echo("Creating package file.")
    time.sleep(15)
    download_asset(config, url, api_path, output)
