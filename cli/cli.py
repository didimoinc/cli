import click
import json
import sys
import time

from .utils import print_key_value, print_status_header, print_status_row
from .network import DidimoAuth, http_get, http_post
from .config import Config
from .helpers import get_didimo_status, download_didimo, URL
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
    api_path = "/v2/didimo/list"
    url = config.api_host + api_path
    r = http_get(url, auth=DidimoAuth(config, api_path))
    if raw:
        click.echo(r.text)
    else:
        if number < 1:
            sys.exit(0)

        didimos = []
        page = 1
        didimos += r.json()['models']
        while page != number:
            next_page = r.json().get('next', None)
            if next_page != None:
                api_path = "/v2" + next_page
                url = config.api_host + api_path
                r = http_get(url, auth=DidimoAuth(config, api_path))
                didimos += r.json()['models']
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
    api_path = "/v2/profile"
    url = config.api_host + api_path
    r = http_get(url, auth=DidimoAuth(config, api_path))
    response = r.json()

    if raw:
        click.echo(r.text)
    else:
        api_path2 = "/v2/didimo/list"
        url2 = config.api_host + api_path2
        r2 = http_get(url2, auth=DidimoAuth(config, api_path2))
        profile = r2.json()
        print_key_value("Tier", response["tier_label"])
        print_key_value("Points", response["points"])
        print_key_value("Available Features", response["available_features"])
        print_key_value("Total didimos in account", profile['total_list_size'])
        expiry_message = "\n(!) %s points will expire at %s" % \
                            (response["next_expiration_points"],
                                response["next_expiration_date"])
        click.secho(expiry_message, fg="yellow", err=True)




@cli.command(short_help="Create a didimo")
@click.argument("type",
                type=click.Choice(["photo",
                                    "lofimesh_texture",
                                    "hifimesh_texture_photo"]),
                required=True, metavar="TYPE")
@click.argument("input", type=click.Path(exists=True), required=True)
@click.option('--feature', '-f', multiple=True,
                type=click.Choice(["basic", "expressions", "visemes", "geometry_objs"]),
                help="Create didimo with optional features. This flag can be used multiple times.")
@click.option('--no-download', '-n', is_flag=True, default=False,
                help="Do not download didimo")
@click.option('--no-wait', '-w', is_flag=True, default=False,
                help="Do not wait for didimo creation and do not download")
@click.option("--output", "-o", type=click.Path(), required=False,
                help="Path to download the didimo. If multiple package types "
                    "are present or if the flags --no-wait or --no-download "
                    "are present, this option is ignored. [default: <ID>.zip]")
@click.option('--package-type', '-p', multiple=True,
                type=click.Choice(["maya", "unity", "webviewer"]), default=["maya"],
                help="Specify output types for this didimo. This flag can be used multiple times.", show_default=True)
@click.option("--version", "-v",
                type=click.Choice(["1.6", "2.0"]),
                default="2.0",
                help="Version of the didimo.", show_default=True)
@pass_api
def new(config, type, input, feature, no_download, no_wait, output, package_type, version):
    """
    Create a didimo

    TYPE is the type of input used to create the didimo. Accepted values are:

    \b
        - photo (input must be a .jpg/.jpeg)
        - lofimesh_texture (input must be a .zip)
        - hifimesh_texture_photo (input must be a .zip)

        For more information on the input types, visit
        https://docs.didimo.co/api/?javascript#new\b

    INPUT is the path to the input file.

    \b
    Examples:
        Create a didimo from a photo
        $ didimo new photo ~/Downloads/leo.jpg
    \b
        Create a didimo with basic animation from a photo
        $ didimo new photo ~/Downloads/leo.jpg -f basic
    \b
        Create a didimo from a high fidelity scan using the testing-trial configuration
        $ didimo --config testing-trial new hifimesh_texture_photo ~/Downloads/scan.zip
    """

    if not feature:
        api_path = "/v2/didimo/new/%s/%s/%s" % (type, ','.join(package_type), version)
    else:
        api_path = "/v2/didimo/new/%s/%s/%s/%s" % (type, ','.join(package_type), version, ','.join(feature))
    url = config.api_host + api_path
    files = {'file': click.open_file(input, 'rb')}
    r = http_post(url, auth=DidimoAuth(config, api_path), files=files)
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
                if response['stt'] == "NOK":
                    click.secho(err=True)
                    click.secho('Error: %s' % response["msg"], err=True, fg='red')
                    sys.exit(1)
                if response['status'] == 'done':
                    break
                time.sleep(2)
        if len(package_type) == 1:
            if not no_download:
                if output == None:
                    output = "%s.zip" % didimo_id
                download_didimo(config, didimo_id, package_type[0], output)




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
        if response["stt"] == "NOK":
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
                type=click.Choice(["maya", "unity", "webviewer"]), default="maya",
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
        output = "%s.zip" % id
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




@execute.command(short_help="Produce high fidelity blendshapes on a didimo")
@click.argument("id", required=True)
@click.option("-r", "--raw", required=False, is_flag=True, default=False,
              help="Do not format output, print raw JSON response from API.")
@pass_api
def blendshapes(config, id, raw):
    """
    Produce high fidelity blendshapes on a didimo

    <ID> is the target didimo ID. When given the "-" character, read the didimo
    ID from STDIN.

    Returns the blendshapes didimo ID that you can use with other commands.
    """
    if id == "-":
        id = sys.stdin.readlines()[0].rstrip()

    api_path = "/v2/didimo/%s/execute/blendshapes" % id
    url = config.api_host + api_path
    r = http_get(url, auth=DidimoAuth(config, api_path))
    response = r.json()
    if raw:
        click.echo(json.dumps(response, indent=4))
    else:
        click.echo(response['key'])




@execute.command(short_help="Deform a model to match a didimo shape")
@click.argument("id", required=True)
@click.argument("vertex", required=True, type=click.Path(exists=True))
@click.option("-r", "--raw", required=False, is_flag=True, default=False,
              help="Do not format output, print raw JSON response from API.")
@pass_api
def vertexdeform(config, id, vertex, raw):
    """
    Deform a model to match a didimo shape

    <ID> is the target didimo ID. When given the "-" character, read the didimo
    ID from STDIN.

    <VERTEX> is your vertex file.

    Returns an ID of the deformed vertex that you can use with other commands.
    """
    if id == "-":
        id = sys.stdin.readlines()[0].rstrip()

    api_path = "/v2/didimo/%s/execute/vertexdeform" % id
    url = config.api_host + api_path
    with click.open_file(vertex, 'rb') as v:
        r = http_post(url, auth=DidimoAuth(config, api_path), data=v)
        response = r.json()
        if raw:
            click.echo(json.dumps(response, indent=4))
        else:
            click.echo(response['key'])
