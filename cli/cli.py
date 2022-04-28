import click
import json
import sys
import time
import requests

from .utils import print_key_value, print_status_header, print_status_row
from .network import DidimoAuth, http_get, http_post, http_post_withphoto
from .config import Config
from .helpers import get_didimo_status, download_didimo, URL, download_asset, get_asset_status, wait_for_dgp_completion
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



def list_features_aux(config):
    """
    Get account features based on the pricing model
    """
    api_path = "/v3/accounts/default/status?ui=cli"
    url = config.api_host + api_path

    r = http_get(url, auth=DidimoAuth(config, api_path))
    response = r.json()

    output = {} #[]
    #click.echo(r.text)
    if "request_configuration_settings" in response:
        requestConfigSettings = response["request_configuration_settings"]
        #click.echo(requestConfigSettings)
        if requestConfigSettings:
            requestConfigObjects = requestConfigSettings["objects"]
            #click.echo(requestConfigObjects)
            #click.echo("")
            if requestConfigObjects:
                for requestConfigObject in requestConfigObjects:
                    feature_name = requestConfigObject["code"]
                    feature_group = requestConfigObject["group"]
                    #click.echo("Feature: "+requestConfigObject["code"])
                    requestConfigOptions = requestConfigObject["options"]
                    output[feature_name] = { "group": feature_group, "options":[], "is_input_type": False}
                    is_boolean = False
                    is_input_type = False

                    if requestConfigOptions:
                        for requestConfigOption in requestConfigOptions:
                            if "type" in requestConfigOption and requestConfigOption["type"] == "boolean":
                                is_boolean = True
                                break
                            if "ui" in requestConfigOption and "is_input_type" in requestConfigOption["ui"] and requestConfigOption["ui"]["is_input_type"] == True:
                                is_input_type = True

                            #click.echo(requestConfigOption)
                            #click.echo(requestConfigOption["label"])
                            if "label" in requestConfigOption:
                                output[feature_name]["options"].append(requestConfigOption["label"])

                    output[feature_name]["is_input_type"] = is_input_type

                    if is_boolean:
                        output[feature_name]["options"] = "boolean" 
                    else:
                        #list is not working properly so let's remove duplicates manually
                        distinct_list = []
                        for item in output[feature_name]["options"]:
                            try:
                                #search for the item
                                index = distinct_list.index(item)
                            except ValueError:
                                #print('item not present')
                                distinct_list.append(item)
                        output[feature_name]["options"] = distinct_list #to remove duplicates
                    #click.echo("----")
                #click.echo(output)
    return output


@cli.command(short_help="List available features for creating a didimo")
@pass_api
def list_features(config):
    """
    List available features for creating a didimo

    Use the `new` command to use these accepted values.

    """

    accepted_input_types = []
    accepted_targets = []
    featureList = list_features_aux(config)

    click.echo("Accepted features are:")
    for item in featureList:
        if "group" in featureList[item]:
            if featureList[item]["is_input_type"] == True: #(str(featureList[item]["group"])) == "recipe":
                accepted_input_types.append(featureList[item]["options"])
            elif str(featureList[item]["group"]) == "targets":
                accepted_targets.append(featureList[item]["options"])
            elif str(featureList[item]["group"]) != "input":
                click.echo(" - "+item+" => "+str(featureList[item]["options"]))

    click.echo("TYPE is the type of input used to create the didimo. Accepted type values are:")
    for item in accepted_input_types:
        if len(item) > 0:
            for sub_item in item:
                click.echo(" - "+str(sub_item))
        else:
            click.echo(" - "+str(item))

    click.echo("Package type is the type of output of the didimo. Accepted target values are:")
    for item in accepted_targets:
        if len(item) > 0:
            for sub_item in item:
                click.echo(" - "+str(sub_item))
        else:
            click.echo(" - "+str(item))


@cli.command(short_help="Create a didimo")
@click.argument("type", 
            #type=click.Choice(["photo"]), 
            required=True, metavar="TYPE")
@click.argument("input", type=click.Path(exists=True), required=True)
#@click.option('--depth', '-d',
#              type=click.Path(), required=False,
#              help="Create didimo with depth")
@click.option('--feature', '-f', multiple=True,
              #type=click.Choice(
              #    ["oculus_lipsync", "simple_poses", "arkit", "aws_polly"]),
              help="Create didimo with optional features. This flag can be used multiple times.")
#@click.option('--max-texture', '-m', multiple=False,
#              type=click.Choice(
#                  ["512", "1024", "2048"]),
#              help="Create didimo with optional max texture dimension. ")
@click.option('--no-download', '-n', is_flag=True, default=False,
              help="Do not download didimo")
@click.option('--no-wait', '-w', is_flag=True, default=False,
              help="Do not wait for didimo creation and do not download")
@click.option("--output", "-o", type=click.Path(), required=False,
              help="Path to download the didimo. If multiple package types "
              "are present or if the flags --no-wait or --no-download "
              "are present, this option is ignored. [default: <ID>.zip]")
@click.option('--package-type', '-p', multiple=True,
#              type=click.Choice(["fbx", "gltf"]),
              help="Specify output types for this didimo. This flag can be used multiple times.", show_default=True)
@click.option("--list-features", "-l",
              is_flag=True,
              help="List the available features that can be requested.", show_default=True)
@click.option('--ignore-cost', is_flag=True,
              default=False,
              help="Do not prompt user to confirm operation cost")
@click.option("--version", "-v",
              type=click.Choice(["2.5"]),
              default="2.5",
              help="Version of the didimo.", show_default=True)
@pass_api
def new(config, type, input, feature, no_download, no_wait, output, package_type, list_features, version, ignore_cost):
    """
    Create a didimo

    TYPE is the type of input used to create the didimo. Use `didimo list-features` to see the accepted values.

    INPUT is the path to the input file.

    \b
        - photo (input must be a .jpg/.jpeg/.png)
        - depth (input must be a .png)

        For more information on the input types, visit
        https://developer.didimo.co/docs/cli\b

    \b
    Examples:

        List available features, accepted input types, and output formats \b

            $ didimo list-features

        Create a didimo from a photo without any extra features\b

            $ didimo new photo /path/input.jpg

        Create a didimo with arkit feature from a photo \b

            $ didimo new photo -f arkit /path/input.jpg

        Create a didimo with max_texture_dimension feature from a photo \b

            $ didimo new photo -f max_texture_dimension=2048 /path/input.jpg

    """

    click.echo("")
    click.echo("Obtaining params list...")
    feature_param = []
    feature_param_value = []
    invalid_param_request = []
    accepted_input_types = []
    accepted_targets = []

    if feature :
        for param in feature:
            param_array = param.split("=", param.count(param))
            feature_param.append(param_array[0])
            if len(param_array) == 1:
                feature_param_value.append("true")
            else:
                feature_param_value.append(param_array[1])
        #click.echo("feature_param: "+str(feature_param))
        #click.echo("feature_param_value: "+str(feature_param_value))

        click.echo("Obtaining feature list...")
        featureList = list_features_aux(config)

        click.echo("Obtaining input types...")
        for item in featureList:
            if "group" in featureList[item]:
                if (str(featureList[item]["group"])) == "recipe":
                    accepted_input_types.append(item)
                elif str(featureList[item]["group"]) == "targets":
                    if len(featureList[item]["options"]) > 0:
                        for sub_item in featureList[item]["options"]:
                            accepted_targets.append(sub_item)
                    else:
                        accepted_targets.append(featureList[item]["options"])
        #click.echo(accepted_input_types)
        #click.echo(accepted_targets)

        click.echo("Crosschecking requested features...")

        for name in feature_param:
            if name not in featureList:
                invalid_param_request.append(name)

        try:
            index = accepted_input_types.index(type)
        except ValueError:
            invalid_param_request.append(type)
            click.echo("Error - input type not supported: "+type)

        if package_type:
            if len(package_type) > 0:
                for item in package_type:
                    try:
                        index = accepted_targets.index(item)
                    except ValueError:
                        invalid_param_request.append(item)
                        click.echo("Error - package type not supported: "+item)
            else:
                try:
                    index = accepted_targets.index(package_type)
                except ValueError:
                    invalid_param_request.append(package_type)
                    click.echo("Error - package type not supported: "+package_type)

        if len(invalid_param_request) > 0:
            click.echo("Error - invalid features requested: "+str(invalid_param_request))
            return

    click.echo("Proceeding...")

    api_path = "/v3/didimos"
    url = config.api_host + api_path

    payload = {
        'input_type': type
    }

    i = 0
    for name in feature_param:
        payload[name] = feature_param_value[i]
        i = i + 1

    if len(package_type) > 0:           
        payload["transfer_formats"] = package_type
    else:
        package_type = "default" #how to get this default value?? glft

    #click.echo("payload: "+str(payload))

    depth = None

    if not ignore_cost:    
        # check how many points a generation will consume before they are consumed 
        # and prompt user to confirm operation before proceeding with the didimo generation request
        r = http_post_withphoto(url+"-cost", config.access_key, payload, input, depth, False)
        is_error = ('status' in r.json() and r.json()['status'] != 201) or ('is_error' in r.json() and r.json()['is_error'])
        if is_error:
            click.echo("ERROR: "+ str(r.json()))
            click.echo("The requested configuration is invalid! Aborting...")
            exit(1);

        estimated_cost = r.json()['cost']
        click.echo("The cost of this operation is: "+str(estimated_cost))
        click.confirm('Are you sure you want to proceed with the didimo creation?', abort=True)
        click.echo("Proceeding...")


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
@click.option("-t", "--timeout", required=False, is_flag=False, default=None,
              help="Set maximum time allowed for the function to complete.")
@pass_api
def hairsdeform(config, input, timeout):
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
    error_status = wait_for_dgp_completion(config, key, timeout)
    if error_status:
        click.echo("There was an error creating package file. Download aborted.")
    else:
        download_asset(config, url, api_path, output)


@execute.command(short_help="Deform a model to match a didimo shape")
@click.argument("vertex", required=True, type=click.Path(exists=True))
@click.argument("user_asset", required=True, type=click.Path(exists=True))
@click.option("-t", "--timeout", required=False, is_flag=False, default=None,
              help="Set maximum time allowed for the function to complete.")
@pass_api
def vertexdeform(config, vertex, user_asset, timeout):
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
    error_status = wait_for_dgp_completion(config, key, timeout)
    if error_status:
        click.echo("There was an error creating package file. Download aborted.")
    else:
        download_asset(config, url, api_path, output)
