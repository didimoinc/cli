import click
import json
import sys
import time
import requests
import zipfile
import os
import re
import shutil

from .utils import print_key_value, print_status_header, print_status_row
from .network import DidimoAuth, http_get, http_post, http_post_withphoto, cache_this_call, clear_network_cache
from .config import Config
from .helpers import get_didimo_status, download_didimo, URL, download_asset, get_asset_status, wait_for_dgp_completion
from ._version import __version__

pass_api = click.make_pass_decorator(Config)

HELP_OPTION_NAMES=['--help', '-h']

# https://click.palletsprojects.com/en/8.1.x/advanced/
@click.help_option(*HELP_OPTION_NAMES)
#@click.pass_context
class MultiVersionCommandGroup(click.Group):
    def get_command(self, ctx, cmd_name):
        if cmd_name == "new":
            # We are only controlling "new"

            Config.load(self, False)
            Config.load_configuration(self, self.configuration)

            api_version = get_api_version(self)
            #print("Current API/DGP Version: "+api_version)

            is_compatible = False
            selected_rule = None
            for rule in get_cli_version_compatibility_rules(self):
                regex_expression = re.compile(rule["pattern"])
                is_compatible = regex_expression.match(api_version)
                if is_compatible:
                    selected_rule = rule
                    break
            
            #if not compatible, user is informed that CLI needs to be updated
            # TODO: This is not a boolean
            #if not is_compatible:
            #    print("Compatibility Error - please update Didimo CLI")
            #    sys.exit(0)

            #api_version_compatibility_rule = get_cli_version_compatibility_rules(self)[0]
            #print(">>>>Compatibility rule: "+str(api_version_compatibility_rule))

            #regex_expression = re.compile(api_version_compatibility_rule)
            #is_compatible = regex_expression.match(api_version)

            method_name = cmd_name + "-" + selected_rule["settings"]["cli_signature"].replace("_", "-")

            command = click.Group.get_command(self, ctx, method_name)

            #if no match is found, user is informed that CLI needs to be updated
            if command is None:
                print("Error - please update Didimo CLI")
                sys.exit(0)

            # Force the name to became the original one
            command.name = "new"
            return command

        return click.Group.get_command(self, ctx, cmd_name)

    def list_commands(self, ctx):
        commands = super().list_commands(ctx)
        # We want "new" (because we need it as a placeholder for `didimo new --help`),
        # but not new-2-5-5, new-2-5-6, etc.
        commands = [
            command
            for command in commands
            if command == "new" or not command.startswith("new-")
        ]
        return commands

@click.command(cls=MultiVersionCommandGroup)
@click.help_option(*HELP_OPTION_NAMES)
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
@click.help_option(*HELP_OPTION_NAMES)
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
@click.help_option(*HELP_OPTION_NAMES)
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
@click.help_option(*HELP_OPTION_NAMES)
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
                    tier_level_restriction = False

                    if "tier_level" in requestConfigObject:
                        output[feature_name]["tier_level_restriction"] = True

                    if requestConfigOptions:
                        for requestConfigOption in requestConfigOptions:
                            if "tier_level" in requestConfigOption:
                                tier_level_restriction = True

                            if "type" in requestConfigOption and requestConfigOption["type"] == "boolean":
                                is_boolean = True
                                break
                            if "ui" in requestConfigOption and "is_input_type" in requestConfigOption["ui"] and requestConfigOption["ui"]["is_input_type"] == True:
                                is_input_type = True

                            #click.echo(requestConfigOption)
                            #click.echo(requestConfigOption["label"])
                            if "label" in requestConfigOption:
                                output[feature_name]["options"].append(requestConfigOption["match"])

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

                    output[feature_name]["tier_level_restriction"] = tier_level_restriction
                    #click.echo("----")
                #click.echo(output)
    return output


#@cli.command(short_help="List available features for creating a didimo")
#@click.help_option(*HELP_OPTION_NAMES)
#@pass_api
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
            elif item == "photo": #HACK: will be removed when the ui provides enough info to ignore this input type as feature
                pass
            elif str(featureList[item]["group"]) == "input":
                click.echo(" - "+item+" => "+"the path to the depth file (which must be a .jpg/.jpeg/.png).")   
            elif "tier_level_restriction" in featureList[item] and featureList[item]["tier_level_restriction"] == True: #options - tier_level RESTRICTION 
                click.echo(" - "+item+" => "+str(featureList[item]["options"])+" - FEATURE OR OPTIONS RESTRICTED BY TIER LEVEL")
            else:#elif str(featureList[item]["group"]) != "input":
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
@pass_api
def new(config):
    """
    Create a didimo
    """
    pass #this is a dummy function just to show up on the main menu


@cli.command(short_help="Create a didimo")
@click.help_option(*HELP_OPTION_NAMES)
@click.argument("input_type", type=click.Choice(["photo", "rgbd"]), required=True, metavar="TYPE")
@click.argument("input", type=click.Path(exists=True), required=True)
@click.option('--depth', '-d',
              type=click.Path(), required=False,
              help="Create didimo with depth.")
@click.option('--feature', '-f', multiple=True,
              type=click.Choice(
                  ["oculus_lipsync", "simple_poses", "arkit", "aws_polly"]),
              help="Create didimo with optional features. This flag can be used multiple times.")
@click.option('--max-texture-dimension', '-m', multiple=False,
              type=click.Choice(
                  ["512", "1024", "2048"]),
              help="Create didimo with optional max texture dimension.")
@click.option('--no-download', '-n', is_flag=True, default=False,
              help="Do not download didimo.")
@click.option('--no-wait', '-w', is_flag=True, default=False,
              help="Do not wait for didimo creation and do not download.")
@click.option("--output", "-o", type=click.Path(), required=False,
              help="Path to download the didimo. If multiple package types "
              "are present or if the flags --no-wait or --no-download "
              "are present, this option is ignored. [default: <ID>.zip]")
@click.option('--package-type', '-p', multiple=True,
              type=click.Choice(["fbx", "gltf"]),
              help="Specify output types for this didimo. This flag can be used multiple times.", show_default=True)
@click.option('--ignore-cost', is_flag=True,
              default=False,
              help="Do not prompt user to confirm operation cost.")
@click.option("--version", "-v",
              type=click.Choice(["2.5"]),
              default="2.5",
              help="Version of the didimo.", show_default=True)
@pass_api
#def new(config, type, input, depth, feature, max_texture, no_download, no_wait, output, package_type, version, ignore_cost):
def new_2_5_2(config, input_type, input, depth, feature, max_texture_dimension, no_download, no_wait, output, package_type, ignore_cost, version):
    """
    Create a didimo

    TYPE is the type of input used to create the didimo. Accepted values are:

    \b
        - photo (input must be a .jpg/.jpeg/.png)
        - rgbd (input must be a .jpg/.jpeg/.png; use -d to provide the depth file, which must be a .png)

        For more information on the input types, visit
        https://developer.didimo.co/docs/cli\b

    INPUT is the path to the input file.

    \b
    Examples:
        Create a didimo from a photo
        $ didimo new photo /path/input.jpg

    """

    api_path = "/v3/didimos"
    url = config.api_host + api_path

    payload = {
#        'input_type': 'photo'
    }

    if input_type != None:
        payload["input_type"] = input_type

    if len(package_type) > 0:
        payload["transfer_formats"] = package_type
        package_type = package_type[0]
    else:
        package_type = "gltf"

    if max_texture_dimension != None:
        payload["max_texture_dimension"] = max_texture_dimension

    for feature_item in feature:
        payload[feature_item] = 'true'
    
    if not ignore_cost:    
        # check how many points a generation will consume before they are consumed 
        # and prompt user to confirm operation before proceeding with the didimo generation request
        
        r = http_post_withphoto(url+"-cost", config.access_key, payload, input, depth)
        
        json_response = r.json()
        is_error = r.json()['is_error'] if 'is_error' in json_response else False
        if is_error:
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
        with click.progressbar(length=100, label='Creating didimo', show_eta=False) as bar:
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
            if output is None:
                output = ""
            else:
                if not output.endswith('/'):
                    output = output + "/"
            download_didimo(config, didimo_id, "", output)


@cli.command(short_help="Create a didimo")
@click.help_option(*HELP_OPTION_NAMES)
@click.argument("input_type", type=click.Choice(["photo", "rgbd"]), required=True, metavar="TYPE")
@click.argument("input", type=click.Path(exists=True), required=True)
@click.option('--depth', '-d',
              type=click.Path(), required=False,
              help="Create didimo with depth.")
@click.option('--feature', '-f', multiple=True,
              type=click.Choice(
                  ["oculus_lipsync", "simple_poses", "arkit", "aws_polly"]),
              help="Create didimo with optional features. This flag can be used multiple times.")
@click.option('--max-texture-dimension', '-m', multiple=False,
              type=click.Choice(
                  ["512", "1024", "2048"]),
              help="Create didimo with optional max texture dimension.")
@click.option('--avatar-structure', multiple=False,
              type=click.Choice(
                  ["head-only", "full-body"]),
              help="Create didimo with avatar structure option.")
@click.option('--garment', multiple=False,
              type=click.Choice(
                  ["none","casual", "sporty"]),
              help="Create didimo with garment option. This option is only available for full-body didimos.")
@click.option('--gender', multiple=False,
              type=click.Choice(
                  ["female", "male", "none"]),
              help="Create didimo with gender option. This option is only available for full-body didimos.")
@click.option('--no-download', '-n', is_flag=True, default=False,
              help="Do not download didimo.")
@click.option('--no-wait', '-w', is_flag=True, default=False,
              help="Do not wait for didimo creation and do not download.")
@click.option("--output", "-o", type=click.Path(), required=False,
              help="Path to download the didimo. If multiple package types "
              "are present or if the flags --no-wait or --no-download "
              "are present, this option is ignored. [default: <ID>.zip]")
@click.option('--package-type', '-p', multiple=True,
              type=click.Choice(["fbx", "gltf"]),
              help="Specify output types for this didimo. This flag can be used multiple times.", show_default=True)
@click.option('--ignore-cost', is_flag=True,
              default=False,
              help="Do not prompt user to confirm operation cost.")
@click.option("--version", "-v",
              type=click.Choice(["2.5"]),
              default="2.5",
              help="Version of the didimo.", show_default=True)
@pass_api
#def new(config, type, input, depth, feature, max_texture, no_download, no_wait, output, package_type, version, ignore_cost):
def new_2_5_6(config, input_type, input, depth, feature, avatar_structure, garment, gender, max_texture_dimension, no_download, no_wait, output, package_type, ignore_cost, version):
    """
    Create a didimo

    TYPE is the type of input used to create the didimo. Accepted values are:

    \b
        - photo (input must be a .jpg/.jpeg/.png)
        - rgbd (input must be a .jpg/.jpeg/.png; use -d to provide the depth file, which must be a .png)

        For more information on the input types, visit
        https://developer.didimo.co/docs/cli\b

    INPUT is the path to the input file.

    \b
    Examples:
        Create a didimo from a photo
        $ didimo new photo /path/input.jpg

    """

    api_path = "/v3/didimos"
    url = config.api_host + api_path

    payload = {
#        'input_type': 'photo'
    }

    if input_type != None:
        payload["input_type"] = input_type

    if avatar_structure != None:
        payload["avatar_structure"] = avatar_structure
    
    if garment != None:
        payload["garment"] = garment

    if gender != None:
        if gender == "none":
            payload["gender"] = ""
        else:
            payload["gender"] = gender


    if len(package_type) > 0:
        payload["transfer_formats"] = package_type
        package_type = package_type[0]
    else:
        package_type = "gltf"

    if max_texture_dimension != None:
        payload["max_texture_dimension"] = max_texture_dimension

    for feature_item in feature:
        payload[feature_item] = 'true'

    if not ignore_cost:    
        # check how many points a generation will consume before they are consumed 
        # and prompt user to confirm operation before proceeding with the didimo generation request
        r = http_post_withphoto(url+"-cost", config.access_key, payload, input, depth)
        json_response = r.json()
        is_error = r.json()['is_error'] if 'is_error' in json_response else False
        if is_error:
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
        with click.progressbar(length=100, label='Creating didimo', show_eta=False) as bar:
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
            if output is None:
                output = ""
            else:
                if not output.endswith('/'):
                    output = output + "/"
            download_didimo(config, didimo_id, "", output)


@cli.command(short_help="Create a didimo")
@click.help_option(*HELP_OPTION_NAMES)
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
@click.option('--ignore-cost', is_flag=True,
              default=False,
              help="Do not prompt user to confirm operation cost")
@click.option("--version", "-v",
              type=click.Choice(["2.5"]),
              default="2.5",
              help="Version of the didimo.", show_default=True)
@pass_api
def new_dynamic(config, type, input, feature, no_download, no_wait, output, package_type, version, ignore_cost):
    """
    Create a didimo

    TYPE is the type of input used to create the didimo. 

    INPUT is the path to the input file (which must be a .jpg/.jpeg/.png).

    \b
    Use `didimo list-features` to see the accepted values.

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

    if True: #feature :
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
                if featureList[item]["is_input_type"] == True: 
                    if len(featureList[item]["options"]) > 0:
                        for sub_item in featureList[item]["options"]:
                            accepted_input_types.append(sub_item.lower())
                    else:
                        accepted_input_types.append(featureList[item]["options"].lower())
                elif str(featureList[item]["group"]) == "targets":
                    if len(featureList[item]["options"]) > 0:
                        for sub_item in featureList[item]["options"]:
                            accepted_targets.append(sub_item.lower())
                    else:
                        accepted_targets.append(featureList[item]["options"].lower())
        #click.echo(accepted_input_types)
        #click.echo(accepted_targets)


        click.echo("Crosschecking requested features...")

        for name in feature_param:
            if name not in featureList:
                invalid_param_request.append(name)

        try:
            index = accepted_input_types.index(type.lower())
        except ValueError:
            invalid_param_request.append(type)
            click.echo("Error - input type not supported: "+type)

        if package_type:
            if len(package_type) > 0:
                for item in package_type:
                    try:
                        index = accepted_targets.index(item.lower())
                    except ValueError:
                        invalid_param_request.append(item)
                        click.echo("Error - package type not supported: "+item)
            else:
                try:
                    index = accepted_targets.index(package_type.lower())
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
        'input_type': type.lower()
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
        with click.progressbar(length=100, label='Creating didimo', show_eta=False) as bar:
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
            if output is None:
                output = ""
            else:
                if not output.endswith('/'):
                    output = output + "/"
            download_didimo(config, didimo_id, "", output)

@cli.command(short_help='Get status of didimos')
@click.help_option(*HELP_OPTION_NAMES)
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
@click.help_option(*HELP_OPTION_NAMES)
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
@click.help_option(*HELP_OPTION_NAMES)
@click.argument("id", required=True)
@click.option("-o", "--output", type=click.Path(),
              help="Output path. [default: <ID>.zip]")
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
        curr_dir = os.getcwd()
        if not curr_dir.endswith('/'):
            curr_dir = curr_dir + "/"

        output = curr_dir
    else:
        if not output.endswith('/'):
            output = output + "/"
    download_didimo(config, id, package_type, output)


@cli.command()
@click.help_option(*HELP_OPTION_NAMES)
@pass_api
def version(config):
    """
    Print CLI version and exit
    """
    print("CLI version: "+__version__)
    sys.exit(0)


@cli.group()
@click.help_option(*HELP_OPTION_NAMES)
@pass_api
def execute(config):
    """
    Execute on-demand features on didimos
    """
    pass


@execute.command(short_help="Produce high fidelity hairs on a didimo")
@click.help_option(*HELP_OPTION_NAMES)
@click.argument("input", type=click.Path(exists=True), required=True)
@click.option("-t", "--timeout", required=False, is_flag=False, default=None,
              help="Set maximum time allowed for the function to complete.")
@pass_api
def hairsdeform(config, input, timeout):
    """
    Produce high fidelity hairstyle deformation for a didimo, given a deformation file

    <INPUT> is the deformation file (.dmx or .zip containing the DMX file).

    The CLI accepts a zip file containing a DMX file, extracting it, or the DMX file directly, 
    and sends it, along with the asset to deform, to the API. 
    
    The output package will be named with a suffix that represents the asset type (“_hairs”). 
    If the input was a zip file from which we are able to decode a didimo key, the output will be named after the original didimo key.

    """

    api_path = "/v3/assets"
    url = config.api_host + api_path

    payload = {
        'input_type': 'hairs_deform'
    }

    filePath = ""
    outputFileSuffix = "_hairs"
    outputFilePrefix = ""

    if input.endswith('.zip'): 
        temp_directory_to_extract_to = "temp"

        shutil.rmtree(temp_directory_to_extract_to, ignore_errors=True)

        with zipfile.ZipFile(input, 'r') as zip_ref:
            zip_ref.extractall(temp_directory_to_extract_to)
            zip_ref.close()

        files=os.listdir(temp_directory_to_extract_to)
        for file in files:
            if file.endswith('.dmx'):
                filePath=temp_directory_to_extract_to+'/'+file
                pathKeySplit = input.replace('.','_').split('_')
                if len(pathKeySplit)>1:
                    pathKey = pathKeySplit[1]
                else: 
                    pathKey = "key"
                outputFilePrefix = pathKey+"_"
    else:
        filePath = input

    if filePath == "":
        click.echo("Error with path to dmx file")        
        return

    files = [('template_deformation', (filePath, open(
        filePath, 'rb'), 'application/octet-stream'))]

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

    curr_dir = os.getcwd()
    if not curr_dir.endswith('/'):
        curr_dir = curr_dir + "/"

    output = "%s.zip" % (curr_dir+ outputFilePrefix + key + outputFileSuffix)

    click.echo("Creating package file.")
    error_status = wait_for_dgp_completion(config, key, timeout)
    if error_status:
        click.echo("There was an error creating package file. Download aborted.")
    else:
        download_asset(config, url, api_path, output)


@execute.command(short_help="Deform a model to match a didimo shape")
@click.help_option(*HELP_OPTION_NAMES)
@click.argument("vertex", required=True, type=click.Path(exists=True))
@click.argument("user_asset", required=True, type=click.Path(exists=True))
@click.option("-t", "--timeout", required=False, is_flag=False, default=None,
              help="Set maximum time allowed for the function to complete.")
@pass_api
def vertexdeform(config, vertex, user_asset, timeout):
    """
    Deform an asset to match a didimo shape

    <VERTEX> is the deformation file (.dmx or .zip containing the DMX file).
    <USER_ASSET> is the asset file to be deformed.

    The CLI accepts a zip file containing a DMX file, extracting it, or the DMX file directly, 
    and sends it, along with the asset to deform, to the API. 
    
    The output package will be named with a suffix that represents the asset type (“_vertexdeformation”). 
    If the vertex input was a zip file from which we are able to decode a didimo key, the output will be named after the original didimo key.

    """

    api_path = "/v3/assets"
    url = config.api_host + api_path

    payload = {'input_type': 'vertex_deform'}

    filePath = ""
    outputFileSuffix = "_vertexdeformation"

    if vertex.endswith('.zip'): 
        temp_directory_to_extract_to = "temp"

        shutil.rmtree(temp_directory_to_extract_to, ignore_errors=True)

        with zipfile.ZipFile(vertex, 'r') as zip_ref:
            zip_ref.extractall(temp_directory_to_extract_to)
            zip_ref.close()

        files=os.listdir(temp_directory_to_extract_to)
        for file in files:
            if file.endswith('.dmx'):
                filePath=temp_directory_to_extract_to+'/'+file
                pathKeySplit = vertex.replace('.','_').split('_')
                if len(pathKeySplit)>1:
                    pathKey = pathKeySplit[1]
                else: 
                    pathKey = "key"
                outputFileSuffix = "_"+pathKey+"_vertexdeformation"
    else:
        filePath = vertex

    if filePath == "":
        click.echo("Error with path to dmx file")        
        return

    files = [
        ('template_deformation', (filePath, open(
            filePath, 'rb'), 'application/octet-stream')),
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

    curr_dir = os.getcwd()
    if not curr_dir.endswith('/'):
        curr_dir = curr_dir + "/"

    output = "%s.zip" % (curr_dir + key + outputFileSuffix)

    click.echo("Creating package file.")
    error_status = wait_for_dgp_completion(config, key, timeout)
    if error_status:
        click.echo("There was an error creating package file. Download aborted.")
    else:
        download_asset(config, url, api_path, output)

def get_api_version(config):
    # Get the current DGP version from the applications using the selected API Key
    api_path = "/v3/accounts/default/applications"
    url = config.api_host + api_path

    #r = http_get(url, auth=DidimoAuth(config, api_path))
    r = cache_this_call(url, config.access_key, auth=DidimoAuth(config, api_path)) 

    if r.status_code != 200:
        click.secho('Error %d' % r.status_code, err=True, fg='red')
        click.echo(r.text)
        sys.exit(1)

    response = r.json()

    for app in response["applications"]:
        if "api_keys" in app:
            for app_key in app["api_keys"]:
                if app_key["key"] == config.access_key:
                    return app["dgp_version"]

    return "api version not found"

def get_cli_version_compatibility_rules(config):
    #Get the current CLI version compatibility rules 

    api_path = "/v3/platforms/cli"
    url = config.api_host + api_path

    #r = http_get(url, auth=DidimoAuth(config, api_path))
    r = cache_this_call(url, config.access_key, auth=DidimoAuth(config, api_path)) 

    if r.status_code != 200:
        click.secho('Error %d' % r.status_code, err=True, fg='red')
        click.echo(r.text)
        sys.exit(1)

    response = r.json()

    #print(response)

    for version in response["versions"]:
        if version["code"] == __version__:
            return version["dgp_compatibility_rules"]

    return "CLI version not found"

    return compatibility_json


@cli.command()
@click.help_option(*HELP_OPTION_NAMES)
@pass_api
def version_api(config):
    """
    Print API/DGP version and exit
    """
    print("API version: "+get_api_version(config))
    sys.exit(0)

@cli.command()
@click.help_option(*HELP_OPTION_NAMES)
@pass_api
def version_cli_compatibility_rules(config):
    """
    Print CLI/DGP version compatibility rules and exit
    """
    print("CLI version - compatibility rules: "+str(get_cli_version_compatibility_rules(config)))
    sys.exit(0)


@cli.command()
@click.help_option(*HELP_OPTION_NAMES)
@pass_api
def clear_cache(config):
    """
    Clears cache and exit
    """
    print("Clearing cache...")
    clear_network_cache() 
    sys.exit(0)

