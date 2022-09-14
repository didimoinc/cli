import click
import json
import sys
import time
import requests
import zipfile
import os
import re
import shutil
import fnmatch
import psutil
import platform
import multiprocessing
from multiprocessing import current_process 
from multiprocessing import Process
from .shared_queue import MyQueue, SharedCounter

from .utils import print_key_value, print_status_header, print_status_row, create_set, print_didimo_generation_template_header, print_didimo_generation_template_row
from .utils import print_bulk_requests_header, print_bulk_requests_row, print_bulk_request_item_header, print_bulk_request_item_row
from .network import DidimoAuth, http_get, http_post, http_post_withphoto, http_post_no_break, http_put, http_delete, cache_this_call, clear_network_cache, http_request_json
from .config import Config
from .helpers import DidimoNotFoundException, get_didimo_status, download_didimo, URL, download_asset, get_asset_status, wait_for_dgp_completion
from .helpers import get_cli_version_compatibility_rules, get_output_display_type_json_flag, list_aux, list_features_aux
from .shared_processing import new_aux_shared_preprocess_batch_files, new_aux_shared_upload_processing_and_download, deformation_aux_shared_processing_and_download
from .shared_processing import get_didimo_generation_template_aux, delete_didimo_generation_template_aux, generation_template_shared_response_processing
from .shared_processing import new_aux_shared_upload_core, bulk_list_aux, bulk_get_aux
from ._version import __version__

pass_api = click.make_pass_decorator(Config)

HELP_OPTION_NAMES=['--help', '-h']

# https://click.palletsprojects.com/en/8.1.x/advanced/
@click.help_option(*HELP_OPTION_NAMES)
#@click.pass_context
class MultiVersionCommandGroup(click.Group):
    def get_command(self, ctx, cmd_name):

        if cmd_name == "new" or cmd_name == "generation-template" or cmd_name == "bulk":
            # We are only controlling "new" (to generate a new didimo) and "create" (to add a new didimo generation template)

            Config.load(self)
            Config.load_configuration(self, self.configuration, False)

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
            command.name = cmd_name #"new"
            return command

        return click.Group.get_command(self, ctx, cmd_name)

    def list_commands(self, ctx):
        commands = super().list_commands(ctx)
        # We want "new" (because we need it as a placeholder for `didimo new --help`),
        # but not new-2-5-5, new-2-5-6, etc.
        commands = [
            command
            for command in commands
            if (command == "new" or not command.startswith("new-")) and not command.startswith("generation-template-") and not command.startswith("bulk-")
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
@click.option('--output-display-type', prompt=True, help="Console output type.", 
                                       type=click.Choice(["human-readable", "json"]), 
                                       default="human-readable", show_default=True)
@pass_api
def init(config, name, host, api_key, api_secret, output_display_type):
    """
    Initializes configuration

    <NAME> is the name of the configuration that will be added.
    """
    config.init(name, host, api_key, api_secret, output_display_type)


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
#@click.option("-n", "--number", required=False, default=1, show_default=True,
#              help="Number of pages to query from the API. Each page has 10 didimos.")
@click.option("-p", "--page-size", required=False, default=20, show_default=True,
              help="Number of didimos per page to query from the API. Default is 20 didimos.")
@click.option("-i", "--index", required=False, default=1, show_default=True,
              help="Page index to query from the API. Default is to show the first page.")
@click.option("-n", "--navigate", required=False,is_flag=True, default=False, show_default=True,
              help="Prompt to continue navigating subsequent pages.")
@click.option("-s", "--sort-by", required=False, default="created_at", show_default=True,
              help="Sort by attribute name.")
@click.option("-o", "--sort-order", required=False, default="descending", show_default=True,
              help="Sorting order of the content. Default is descending.")
@click.option('--output-display-type', help="Console output type.", 
                                       type=click.Choice(["human-readable", "json"]), 
                                       show_default=False)
@pass_api
def list(config, page_size, index, navigate, sort_by, sort_order, output_display_type):
    """
    List didimos
    """
    api_path = "/v3/didimos/"
    list_aux(config, api_path, page_size, index, navigate, sort_by, sort_order, output_display_type)

@cli.command()
@click.help_option(*HELP_OPTION_NAMES)
@click.option("-n", "--number", required=False, default=1, show_default=True,
              help="Number of pages to query from the API. Each page has 10 didimos.")
#@click.option("-r", "--raw", required=False, is_flag=True, default=False,
#              help="Do not format output, print raw JSON response from API, ignoring --number.")
@click.option('--output-display-type', help="Console output type.", 
                                       type=click.Choice(["human-readable", "json"]), 
                                       show_default=False)
@pass_api
def list_demo_didimos(config, number, output_display_type):
    """
    List demo didimos
    """
    api_path = "/v3/didimos/demos"
    list_aux(config, api_path, 10, number, False, "created_at", "descending", output_display_type)


@cli.command()
@click.help_option(*HELP_OPTION_NAMES)
#@click.option("-r", "--raw", required=False, is_flag=True, default=False,
#              help="Do not format output, print raw JSON response from API.")
@click.option('--output-display-type', help="Console output type.", 
                                       type=click.Choice(["human-readable", "json"]), 
                                       show_default=False)
@pass_api
def account(config, output_display_type):
    """
    Get account information
    """

    output_display_type_json_flag = get_output_display_type_json_flag(config, output_display_type)

    api_path = "/v3/accounts/default/status"
    url = config.api_host + api_path

    r = http_get(url, auth=DidimoAuth(config, api_path))
    response = r.json()
    
    if output_display_type_json_flag:
        click.echo(r.text)
    else:

        #tier = response["tier"]["name"]
        #print (response["owner_profile_uuid"])
        #print (tier)

        api_path2 = "/v3/didimos?order_by=-created_at"
        url2 = config.api_host + api_path2

        #print (url2)
        
        r2 = http_get(url2, auth=DidimoAuth(config, api_path2))
        didimos = r2.json()
        
        print_key_value("Tier", response["tier"]["name"])
        print_key_value("Points", response["balance"])
        print_key_value("Total didimos in account", didimos['total_size'])
        if "next_expiration_points" in response and "next_expiration_date" in response:
            expiry_message = "\n(!) %s points will expire at %s" % \
                (response["next_expiration_points"],
                response["next_expiration_date"])
            click.secho(expiry_message, fg="yellow", err=True)


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


#####################################
#
# Didimo Creation
#
######################################

@cli.command(short_help="Create a didimo")
@pass_api
def new(config):
    """
    Create a didimo
    """
    pass #this is a dummy function just to show up on the main menu

@cli.command(short_help="Create a didimo")
@click.help_option(*HELP_OPTION_NAMES)
@click.argument("input", type=click.Path(exists=True), required=True)
@click.argument("input_type", type=click.Choice(["photo", "rgbd"]), required=False, metavar="TYPE")
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
                  ["female", "male", "auto"]),
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
@click.option('--output-display-type', help="Console output type.", 
                                       type=click.Choice(["human-readable", "json"]), 
                                       show_default=False)
@click.option('--template', help="Didimo generation template UUID.", required=False)
@pass_api
def new_2_5_7(config, input_type, input, depth, feature, avatar_structure, garment, gender, max_texture_dimension, no_download, no_wait, output, package_type, ignore_cost, output_display_type, template):
    """
    Create a didimo

    TYPE is the type of input used to create the didimo. Accepted values are:

    \b
        - photo (input must be a .jpg/.jpeg/.png)
        - rgbd (input must be a .jpg/.jpeg/.png; use -d to provide the depth file, which must be a .png)

        For more information on the input types, visit
        https://developer.didimo.co/docs/cli\b

    INPUT is the path to the input file (which must be a .jpg/.jpeg/.png/.zip or a directory containing photos)

    TEMPLATE_UUID is the didimo generation template UUID. The specified options and arguments will override the template values accordingly.\n

    \b
    Examples:
        Create a didimo from a photo
        $ didimo new /path/input.jpg photo
    """
    template_uuid = template
    output_display_type_json_flag = get_output_display_type_json_flag(config, output_display_type)

    if output_display_type_json_flag and ignore_cost == False:
        click.secho("The command configuration is invalid! You must explicitly ignore the cost prompt by setting the ignore cost flag in order to use JSON as the output display type. Aborting...", err=True, fg='red')
        exit(1);

    if template_uuid != None:
        #get didimo generation template so that we can override values as commanded
        r = get_didimo_generation_template_aux(config, template_uuid, output_display_type, True)
        if r.status_code != 200:
            if output_display_type_json_flag:
                click.echo( {
                                "error": 1,
                                "template_uuid":template_uuid,
                                "message":"There was an error accessing the didimo generation template with the provided uuid: "+template_uuid
                           })
            else:
                click.echo("There was an error accessing the didimo generation template with the provided uuid: %s" % template_uuid, err=True) 
            exit(1);
        else:   
            payload = json.loads(r.json()["settings"])
            if "input_type" not in payload and input_type == None:
                click.echo( {
                                "error": 1,
                                "input_type":input_type,
                                "message":"The command configuration is invalid! Input type is missing. Aborting..."
                           })
                exit(1);
            elif input_type == None and "input_type" in payload:
                input_type = payload["input_type"]
    elif input_type == None:
        click.echo( {
                        "error": 1,
                        "input_type":input_type,
                        "message":"The command configuration is invalid! Input type is not defined. Aborting..."
                   })
        exit(1);
    else:
        payload = {} 

    batch_files = new_aux_shared_preprocess_batch_files(input, input_type, output_display_type_json_flag)

    api_path = "/v3/didimos"
    url = config.api_host + api_path

    if input_type != None:
        payload["input_type"] = input_type

    if avatar_structure != None:
        payload["avatar_structure"] = avatar_structure
    
    if garment != None:
        payload["garment"] = garment

    if gender != None:
        payload["gender"] = gender

    if len(package_type) > 0:
        payload["transfer_formats"] = package_type

    if max_texture_dimension != None:
        payload["max_texture_dimension"] = max_texture_dimension

    for feature_item in feature:
        payload[feature_item] = 'true'

    if not ignore_cost:    
        # check how many points a generation will consume before they are consumed 
        # and prompt user to confirm operation before proceeding with the didimo generation request
        if batch_files != None:
            r = http_post_withphoto(url+"-cost", config.access_key, payload, batch_files[0], depth)
        else:
            r = http_post_withphoto(url+"-cost", config.access_key, payload, input, depth)

        json_response = r.json()
        is_error = r.json()['is_error'] if 'is_error' in json_response else False
        if is_error:
            click.echo("The requested configuration is invalid! Aborting...")
            exit(1);

        estimated_cost = r.json()['cost']

        if batch_files != None:
            total_estimated_cost = estimated_cost * len(batch_files)
            click.echo("The cost of each didimo generation is: "+str(estimated_cost))
            click.echo("The total cost of this batch operation is: "+str(total_estimated_cost))
        else:
            click.echo("The cost of this operation is: "+str(estimated_cost))
        
        click.confirm('Are you sure you want to proceed with the didimo creation?', abort=True)
        click.echo("Proceeding...")

    batch_flag = True
    if batch_files == None:
        batch_files = [input]
        batch_flag = False

    new_aux_shared_upload_processing_and_download(config, url, batch_files, depth, payload, no_wait, no_download, output, batch_flag, output_display_type_json_flag)


@cli.command(short_help="Create a didimo")
@click.help_option(*HELP_OPTION_NAMES)
@click.argument("input", type=click.Path(exists=True), required=True)
@click.argument("input_type", type=click.Choice(["photo", "rgbd"]), required=False, metavar="TYPE")
@click.option('--depth', '-d',
              type=click.Path(), required=False,
              help="Create didimo with depth.")
@click.option('--feature', '-f', multiple=True,
              type=click.Choice(
                  ["oculus_lipsync", "simple_poses", "arkit", "aws_polly"]),
              help="Create didimo with optional features. This flag can be used multiple times.")
@click.option('--avatar-structure', multiple=False,
              type=click.Choice(
                  ["head-only", "full-body"]),
              help="Create didimo with avatar structure option.")
@click.option('--garment', multiple=False,
              type=click.Choice(
                  ["none","casual", "sporty", "business"]),
              help="Create didimo with garment option. This option is only available for full-body didimos.")
@click.option('--gender', multiple=False,
              type=click.Choice(
                  ["female", "male", "auto"]),
              help="Create didimo with gender option. This option is only available for full-body didimos.")
@click.option('--hair', multiple=False,
              type=click.Choice(
                  ["baseball_cap", 
                  "hair_001",  
                  "hair_002", 
                  "hair_003", 
                  "hair_004", 
                  "hair_005", 
                  "hair_006", 
                  "hair_007", 
                  "hair_008", 
                  "hair_009", 
                  "hair_010", 
                  "hair_011"]),
              help="Create didimo with hair option.")
@click.option('--body-pose', '-bp',
              type=click.Choice(["A", "T"]),
              help="Specify body pose for this didimo. This option is only available for full-body didimos.", show_default=False)
@click.option('--profile', 
              type=click.Choice(["standard", "optimized"]),
              help="Specify a profile to drive this didimo generation.", show_default=False)
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
@click.option('--output-display-type', help="Console output type.", 
                                       type=click.Choice(["human-readable", "json"]), 
                                       show_default=False)
@click.option('--template', help="Didimo generation template UUID.", required=False)
@pass_api
def new_2_5_10(config, input_type, input, depth, feature, avatar_structure, garment, gender, hair, body_pose, profile, no_download, no_wait, output, package_type, ignore_cost, output_display_type, template):
    """
    Create a didimo

    TYPE is the type of input used to create the didimo. Accepted values are:

    \b
        - photo (input must be a .jpg/.jpeg/.png)
        - rgbd (input must be a .jpg/.jpeg/.png; use -d to provide the depth file, which must be a .png)

        For more information on the input types, visit
        https://developer.didimo.co/docs/cli\b

    INPUT is the path to the input file (which must be a .jpg/.jpeg/.png/.zip or a directory containing photos)

    TEMPLATE_UUID is the didimo generation template UUID. The specified options and arguments will override the template values accordingly.\n

    \b
    Examples:
        Create a didimo from a photo
        $ didimo new /path/input.jpg photo
    """
    template_uuid = template
    output_display_type_json_flag = get_output_display_type_json_flag(config, output_display_type)

    if output_display_type_json_flag and ignore_cost == False:
        #click.secho("The command configuration is invalid! You must explicitly ignore the cost prompt by setting the ignore cost flag in order to use JSON as the output display type. Aborting...", err=True, fg='red')
        click.echo( {
                                "error": 1,
                                "input":input,
                                "message":"The command configuration is invalid! You must explicitly ignore the cost prompt by setting the ignore cost flag in order to use JSON as the output display type. Aborting..."
                           })
        exit(1);

    if template_uuid != None:
        #get didimo generation template so that we can override values as commanded
        r = get_didimo_generation_template_aux(config, template_uuid, output_display_type, True)
        if r.status_code != 200:
            if output_display_type_json_flag:
                click.echo( {
                                "error": 1,
                                "template_uuid":template_uuid,
                                "message":"There was an error accessing the didimo generation template with the provided uuid: "+template_uuid
                           })
            else:
                click.echo("There was an error accessing the didimo generation template with the provided uuid: %s" % template_uuid, err=True) 
            exit(1);
        else:   
            payload = json.loads(r.json()["settings"])
            if "input_type" not in payload and input_type == None:
                click.echo( {
                                "error": 1,
                                "input_type":input_type,
                                "message":"The command configuration is invalid! Input type is missing. Aborting..."
                           })
                exit(1);
            elif input_type == None and "input_type" in payload:
                input_type = payload["input_type"]
    elif input_type == None:
        click.echo( {
                        "error": 1,
                        "input_type":input_type,
                        "message":"The command configuration is invalid! Input type is not defined. Aborting..."
                   })
        exit(1);
    else:
        payload = {} 

    batch_files = new_aux_shared_preprocess_batch_files(input, input_type, output_display_type_json_flag)

    api_path = "/v3/didimos"
    url = config.api_host + api_path

    if input_type != None:
        payload["input_type"] = input_type

    if avatar_structure != None:
        payload["avatar_structure"] = avatar_structure
    
    if garment != None:
        payload["garment"] = garment

    if gender != None:
        payload["gender"] = gender

    if hair != None:
        payload["hair"] = hair

    if body_pose != None:
        if avatar_structure == "full-body":
            payload["body_pose"] = body_pose
        else:
            click.echo("The body pose feature is only available for full body didimos.", err=True)
            exit(1);
    
    if profile != None:
        payload["profile"] = profile

    if len(package_type) > 0:
        payload["transfer_formats"] = package_type

    for feature_item in feature:
        payload[feature_item] = 'true'

    if not ignore_cost:    
        # check how many points a generation will consume before they are consumed 
        # and prompt user to confirm operation before proceeding with the didimo generation request
        if batch_files != None:
            r = http_post_withphoto(url+"-cost", config.access_key, payload, batch_files[0], depth)
        else:
            r = http_post_withphoto(url+"-cost", config.access_key, payload, input, depth)

        json_response = r.json()
        is_error = r.json()['is_error'] if 'is_error' in json_response else False
        if is_error:
            click.echo("The requested configuration is invalid! Aborting...")
            exit(1);

        estimated_cost = r.json()['cost']

        if batch_files != None:
            total_estimated_cost = estimated_cost * len(batch_files)
            click.echo("The cost of each didimo generation is: "+str(estimated_cost))
            click.echo("The total cost of this batch operation is: "+str(total_estimated_cost))
        else:
            click.echo("The cost of this operation is: "+str(estimated_cost))
        
        click.confirm('Are you sure you want to proceed with the didimo creation?', abort=True)
        click.echo("Proceeding...")

    batch_flag = True
    if batch_files == None:
        batch_files = [input]
        batch_flag = False

    new_aux_shared_upload_processing_and_download(config, url, batch_files, depth, payload, no_wait, no_download, output, batch_flag, output_display_type_json_flag)



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
@click.option('--output-display-type', help="Console output type.", 
                                       type=click.Choice(["human-readable", "json"]), 
                                       show_default=False)
@pass_api
def new_dynamic(config, type, input, feature, no_download, no_wait, output, package_type, ignore_cost, output_display_type):
    """
    Create a didimo

    TYPE is the type of input used to create the didimo. 

    INPUT is the path to the input file (which must be a .jpg/.jpeg/.png/.zip or a directory containing photos).

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
    output_display_type_json_flag = get_output_display_type_json_flag(config, output_display_type)

    if output_display_type_json_flag and ignore_cost == False:
        click.secho("The command configuration is invalid! You must explicitly ignore the cost prompt by setting the ignore cost flag in order to use JSON as the output display type. Aborting...", err=True, fg='red')
        exit(1);

    batch_files = new_aux_shared_preprocess_batch_files(input, input_type, output_display_type_json_flag)

    if not output_display_type_json_flag:
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

        if not output_display_type_json_flag:
            click.echo("Obtaining feature list...")
        featureList = list_features_aux(config)

        if not output_display_type_json_flag:
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

        if not output_display_type_json_flag:
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

    if not output_display_type_json_flag:
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

    depth = None

    if not ignore_cost:    
        # check how many points a generation will consume before they are consumed 
        # and prompt user to confirm operation before proceeding with the didimo generation request
        if batch_files != None:
            r = http_post_withphoto(url+"-cost", config.access_key, payload, batch_files[0], depth, None, False)
        else:
            r = http_post_withphoto(url+"-cost", config.access_key, payload, input, depth, None, False)

        is_error = ('status' in r.json() and r.json()['status'] != 201) or ('is_error' in r.json() and r.json()['is_error'])
        if is_error:
            click.echo("ERROR: "+ str(r.json()))
            click.echo("The requested configuration is invalid! Aborting...")
            exit(1);

        estimated_cost = r.json()['cost']

        if batch_files != None:
            total_estimated_cost = estimated_cost * len(batch_files)
            click.echo("The cost of each didimo generation is: "+str(estimated_cost))
            click.echo("The total cost of this batch operation is: "+str(total_estimated_cost))
        else:
            click.echo("The cost of this operation is: "+str(estimated_cost))
        
        click.confirm('Are you sure you want to proceed with the didimo creation?', abort=True)
        click.echo("Proceeding...")

    batch_flag = True
    if batch_files == None:
        batch_files = [input]
        batch_flag = False

    new_aux_shared_upload_processing_and_download(config, url, batch_files, depth, payload, no_wait, no_download, output, batch_flag, output_display_type_json_flag)

#####################################
#
# BULK REQUESTS
#
######################################

@cli.group()
@click.help_option(*HELP_OPTION_NAMES)
@pass_api
def bulk(config):
    """
    Perform bulk requests related operations
    """
    pass

@cli.group()
@click.help_option(*HELP_OPTION_NAMES)
@pass_api
def bulk_2_5_7(config):
    """
    Perform bulk requests related operations on DGP compatible version 2.5.7
    """
    pass

@cli.group()
@click.help_option(*HELP_OPTION_NAMES)
@pass_api
def bulk_2_5_10(config):
    """
    Perform bulk requests related operations on DGP compatible version 2.5.10
    """
    pass

#### LIST ########################

@bulk_2_5_7.command(short_help='List bulk requests')
@click.help_option(*HELP_OPTION_NAMES)
@click.argument("group_type", type=click.Choice(["didimos"]), required=True, metavar="GROUP")
@click.option("--filter","-f", multiple=False, help="Filter by status.")
@click.option('--output-display-type', help="Console output type.", 
                                       type=click.Choice(["human-readable", "json"]), 
                                       show_default=False)
@pass_api
def list(config, group_type, filter, output_display_type):
    """
    List bulk requests on DGP compatible version 2.5.7
    """
    bulk_list_aux(config, group_type, filter, output_display_type)

@bulk_2_5_10.command(short_help='List bulk requests')
@click.help_option(*HELP_OPTION_NAMES)
@click.argument("group_type", type=click.Choice(["didimos"]), required=True, metavar="GROUP")
@click.option("--filter","-f", multiple=False, help="Filter by status.")
@click.option('--output-display-type', help="Console output type.", 
                                       type=click.Choice(["human-readable", "json"]), 
                                       show_default=False)
@pass_api
def list(config, group_type, filter, output_display_type):
    """
    List bulk requests on DGP compatible version 2.5.10
    """
    bulk_list_aux(config, group_type, filter, output_display_type)

##### GET ###########################

@bulk_2_5_7.command(short_help='Get bulk request details')
@click.help_option(*HELP_OPTION_NAMES)
@click.argument("group_type", type=click.Choice(["didimos"]), required=True, metavar="GROUP")
@click.argument("uuid", required=True)
@click.option('--output-display-type', help="Console output type.", 
                                       type=click.Choice(["human-readable", "json"]), 
                                       show_default=False)
@pass_api
def get(config, group_type, uuid, output_display_type):
    """
    Get bulk request details on DGP compatible version 2.5.7

    UUID is the bulk request UUID.
    """
    bulk_get_aux(config, group_type, uuid, output_display_type)

@bulk_2_5_10.command(short_help='Get bulk request details')
@click.help_option(*HELP_OPTION_NAMES)
@click.argument("group_type", type=click.Choice(["didimos"]), required=True, metavar="GROUP")
@click.argument("uuid", required=True)
@click.option('--output-display-type', help="Console output type.", 
                                       type=click.Choice(["human-readable", "json"]), 
                                       show_default=False)
@pass_api
def get(config, group_type, uuid, output_display_type):
    """
    Get bulk request details on DGP compatible version 2.5.10

    UUID is the bulk request UUID.
    """
    bulk_get_aux(config, group_type, uuid, output_display_type)

#### CREATE NEW BULK REQUEST ########

@bulk_2_5_7.command(short_help="Create a bulk request")
@click.help_option(*HELP_OPTION_NAMES)
@click.argument("group_type", type=click.Choice(["didimos"]), required=True, metavar="GROUP")
@click.argument("input", type=click.Path(exists=True), required=True)
@click.argument("input_type", type=click.Choice(["photo"]), required=False, metavar="TYPE")
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
                  ["none","casual", "sporty", "business"]),
              help="Create didimo with garment option. This option is only available for full-body didimos.")
@click.option('--gender', multiple=False,
              type=click.Choice(
                  ["female", "male", "auto"]),
              help="Create didimo with gender option. This option is only available for full-body didimos.")

@click.option('--package-type', '-p', multiple=True,
              type=click.Choice(["fbx", "gltf"]),
              help="Specify output types for this didimo. This flag can be used multiple times.", show_default=True)
@click.option('--ignore-cost', is_flag=True,
              default=False,
              help="Do not prompt user to confirm operation cost.")
@click.option('--output-display-type', help="Console output type.", 
                                       type=click.Choice(["human-readable", "json"]), 
                                       show_default=False)
@click.option('--template', help="Didimo generation template UUID.", required=False)
@pass_api
def new(config, group_type, input, input_type, feature, avatar_structure, garment, gender, max_texture_dimension, package_type, ignore_cost, output_display_type, template):
    """
    Create a bulk request on DGP compatible version 2.5.7

    GROUP is the type of object produced. Accepted values are:

    \b
        - didimos (input must be an archive containing image files: .jpg/.jpeg/.png)

    INPUT is the path to the input file (which must be a .zip containing photos, according to the didimos group type)

    INPUT TYPE is the type of the files used to produce didimos (which must be a image file: .jpg/.jpeg/.png). Accepted values are:

    \b
        - photo (input must be image files: .jpg/.jpeg/.png)

        For more information on this operation, visit
        https://developer.didimo.co/docs/cli\b

    TEMPLATE_UUID is the didimo generation template UUID. The specified options and arguments will override the template values accordingly.\n

    \b
    Examples:
        Create a bulk request to generate didimos from a zip of photos
        $ didimo bulk new didimos /path/input.zip photo
    """
    template_uuid = template
    output_display_type_json_flag = get_output_display_type_json_flag(config, output_display_type)

    if output_display_type_json_flag and ignore_cost == False:
        #click.secho("The command configuration is invalid! You must explicitly ignore the cost prompt by setting the ignore cost flag in order to use JSON as the output display type. Aborting...", err=True, fg='red')
        click.echo( {
                                "error": 1,
                                "input":input,
                                "message":"The command configuration is invalid! You must explicitly ignore the cost prompt by setting the ignore cost flag in order to use JSON as the output display type. Aborting..."
                           })
        exit(1);

    if template_uuid != None:
        #pre-validate that the user can access the didimo generation template 
        r = get_didimo_generation_template_aux(config, template_uuid, output_display_type, True)
        if r.status_code != 200:
            if output_display_type_json_flag:
                click.echo( {
                                "error": 1,
                                "template_uuid":template_uuid,
                                "message":"There was an error accessing the didimo generation template with the provided uuid: "+template_uuid
                           })
            else:
                click.echo("There was an error accessing the didimo generation template with the provided uuid: %s" % template_uuid, err=True) 
            exit(1);
        else:   
            payload = json.loads(r.json()["settings"])
            if "input_type" not in payload and input_type == None:
                click.echo( {
                                "error": 1,
                                "input_type":input_type,
                                "message":"The command configuration is invalid! Input type is missing. Aborting..."
                           })
                exit(1);
            elif input_type == None and "input_type" in payload:
                input_type = payload["input_type"]
    elif input_type == None:
        click.echo( {
                        "error": 1,
                        "input_type":input_type,
                        "message":"The command configuration is invalid! Input type is not defined. Aborting..."
                   })
        exit(1);
    else:
        payload = {} 

    if not input.endswith(".zip"):
        if output_display_type_json_flag:
            click.echo( {
                        "error": 1,
                        "input":input,
                        "message":"The input must point to a Zip file."
                        })
        else:
            click.secho('\nError: The input must point to a Zip file.', err=True, fg='red')
        exit(1);

    batch_files = new_aux_shared_preprocess_batch_files(input, input_type, output_display_type_json_flag)

    if batch_files == None:
        if output_display_type_json_flag:
            click.echo( {
                        "error": 1,
                        "input":input,
                        "message":"The input is invalid! Zip verification failed. Aborting..."
                        })
        else:
            click.secho('\nError: The input is invalid! Zip verification failed. Aborting...', err=True, fg='red')
        exit(1);

    api_path = "/v3/"+group_type+"/bulks"
    url = config.api_host + api_path

    if input_type != None:
        payload["input_type"] = input_type

    if avatar_structure != None:
        payload["avatar_structure"] = avatar_structure
    
    if garment != None:
        payload["garment"] = garment

    if gender != None:
        payload["gender"] = gender
    
    if len(package_type) > 0:
        payload["transfer_formats"] = package_type

    if max_texture_dimension != None:
        payload["max_texture_dimension"] = max_texture_dimension

    for feature_item in feature:
        payload[feature_item] = 'true'

    depth = None

    if not ignore_cost:    
        # estimate how many points a generation will consume before they are consumed 
        # and prompt user to confirm operation before proceeding with the bulk request
        cost_estimation_api_path = "/v3/didimos-cost"
        cost_estimation_url = config.api_host + cost_estimation_api_path
        r = http_post_withphoto(cost_estimation_url, config.access_key, payload, batch_files[0], depth)

        json_response = r.json()
        is_error = r.json()['is_error'] if 'is_error' in json_response else False
        if is_error:
            click.echo("The requested configuration is invalid! Aborting...")
            exit(1);

        estimated_cost = r.json()['cost']

        total_estimated_cost = estimated_cost * len(batch_files)
        click.echo("The cost of each didimo generation is: "+str(estimated_cost))
        click.echo("The total cost of this bulk operation is: "+str(total_estimated_cost))
        
        click.confirm('Are you sure you want to proceed with the didimo creation?', abort=True)
        click.echo("Proceeding...")

    r = new_aux_shared_upload_core(config, url, input, depth, input, payload, output_display_type_json_flag)
    r_json = r
    if r_json['error'] == 1:
        upload_error_response = r
        if output_display_type_json_flag:
            click.secho("%s"%str(r_json), fg="red", err=True)
        else:
            click.secho('\nError %d uploading %s: \n%s' % (r.status_code, input, r.text), err=True, fg='red')
    else:
        if output_display_type_json_flag:
            click.secho("%s"%str(r_json), fg="blue", err=False)
        else:
            click.secho('\nCreated bulk from %s: \n%s' % (input, str(r_json)), err=False, fg='blue')


@bulk_2_5_10.command(short_help="Create a bulk request")
@click.help_option(*HELP_OPTION_NAMES)
@click.argument("group_type", type=click.Choice(["didimos"]), required=True, metavar="GROUP")
@click.argument("input", type=click.Path(exists=True), required=True)
@click.argument("input_type", type=click.Choice(["photo"]), required=False, metavar="TYPE")
@click.option('--feature', '-f', multiple=True,
              type=click.Choice(
                  ["oculus_lipsync", "simple_poses", "arkit", "aws_polly"]),
              help="Create didimo with optional features. This flag can be used multiple times.")
@click.option('--avatar-structure', multiple=False,
              type=click.Choice(
                  ["head-only", "full-body"]),
              help="Create didimo with avatar structure option.")
@click.option('--garment', multiple=False,
              type=click.Choice(
                  ["none","casual", "sporty", "business"]),
              help="Create didimo with garment option. This option is only available for full-body didimos.")
@click.option('--gender', multiple=False,
              type=click.Choice(
                  ["female", "male", "auto"]),
              help="Create didimo with gender option. This option is only available for full-body didimos.")
@click.option('--hair', multiple=False,
              type=click.Choice(
                  ["baseball_cap", 
                  "hair_001","hair_002","hair_003","hair_004","hair_005","hair_006","hair_007","hair_008","hair_009","hair_010","hair_011"]),
              help="Create didimo with hair option.")
@click.option('--body-pose', '-bp',
              type=click.Choice(["A", "T"]),
              help="Specify body pose for this didimo. This option is only available for full-body didimos.", show_default=False)
@click.option('--profile',
              type=click.Choice(["standard", "optimized"]),
              help="Specify a profile to drive this didimo generation.", show_default=False)
@click.option('--package-type', '-p', multiple=True,
              type=click.Choice(["fbx", "gltf"]),
              help="Specify output types for this didimo. This flag can be used multiple times.", show_default=True)
@click.option('--ignore-cost', is_flag=True,
              default=False,
              help="Do not prompt user to confirm operation cost.")
@click.option('--output-display-type', help="Console output type.", 
                                       type=click.Choice(["human-readable", "json"]), 
                                       show_default=False)
@click.option('--template', help="Didimo generation template UUID.", required=False)
@pass_api
def new(config, group_type, input, input_type, feature, avatar_structure, garment, gender, hair, body_pose, profile, package_type, ignore_cost, output_display_type, template):
    """
    Create a bulk request on DGP compatible version 2.5.10

    GROUP is the type of object produced. Accepted values are:

    \b
        - didimos (input must be an archive containing image files: .jpg/.jpeg/.png)

    INPUT is the path to the input file (which must be a .zip containing photos, according to the didimos group type)

    INPUT TYPE is the type of the files used to produce didimos (which must be a image file: .jpg/.jpeg/.png). Accepted values are:

    \b
        - photo (input must be image files: .jpg/.jpeg/.png)

        For more information on this operation, visit
        https://developer.didimo.co/docs/cli\b

    TEMPLATE_UUID is the didimo generation template UUID. The specified options and arguments will override the template values accordingly.\n

    \b
    Examples:
        Create a bulk request to generate didimos from a zip of photos
        $ didimo bulk new didimos /path/input.zip photo
    """
    template_uuid = template
    output_display_type_json_flag = get_output_display_type_json_flag(config, output_display_type)

    if output_display_type_json_flag and ignore_cost == False:
        #click.secho("The command configuration is invalid! You must explicitly ignore the cost prompt by setting the ignore cost flag in order to use JSON as the output display type. Aborting...", err=True, fg='red')
        click.echo( {
                                "error": 1,
                                "input":input,
                                "message":"The command configuration is invalid! You must explicitly ignore the cost prompt by setting the ignore cost flag in order to use JSON as the output display type. Aborting..."
                           })
        exit(1);

    if template_uuid != None:
        #pre-validate that the user can access the didimo generation template 
        r = get_didimo_generation_template_aux(config, template_uuid, output_display_type, True)
        if r.status_code != 200:
            if output_display_type_json_flag:
                click.echo( {
                                "error": 1,
                                "template_uuid":template_uuid,
                                "message":"There was an error accessing the didimo generation template with the provided uuid: "+template_uuid
                           })
            else:
                click.echo("There was an error accessing the didimo generation template with the provided uuid: %s" % template_uuid, err=True) 
            exit(1);
        else:   
            payload = json.loads(r.json()["settings"])
            if "input_type" not in payload and input_type == None:
                click.echo( {
                                "error": 1,
                                "input_type":input_type,
                                "message":"The command configuration is invalid! Input type is missing. Aborting..."
                           })
                exit(1);
            elif input_type == None and "input_type" in payload:
                input_type = payload["input_type"]
    elif input_type == None:
        click.echo( {
                        "error": 1,
                        "input_type":input_type,
                        "message":"The command configuration is invalid! Input type is not defined. Aborting..."
                   })
        exit(1);
    else:
        payload = {} 

    if not input.endswith(".zip"):
        if output_display_type_json_flag:
            click.echo( {
                        "error": 1,
                        "input":input,
                        "message":"The input must point to a Zip file."
                        })
        else:
            click.secho('\nError: The input must point to a Zip file.', err=True, fg='red')
        exit(1);

    batch_files = new_aux_shared_preprocess_batch_files(input, input_type, output_display_type_json_flag)

    if batch_files == None:
        if output_display_type_json_flag:
            click.echo( {
                        "error": 1,
                        "input":input,
                        "message":"The input is invalid! Zip verification failed. Aborting..."
                        })
        else:
            click.secho('\nError: The input is invalid! Zip verification failed. Aborting...', err=True, fg='red')
        exit(1);

    api_path = "/v3/"+group_type+"/bulks"
    url = config.api_host + api_path

    if input_type != None:
        payload["input_type"] = input_type

    if avatar_structure != None:
        payload["avatar_structure"] = avatar_structure
    
    if garment != None:
        payload["garment"] = garment

    if gender != None:
        payload["gender"] = gender

    if hair != None:
        payload["hair"] = hair

    if body_pose != None:
        if avatar_structure == "full-body":
            payload["body_pose"] = body_pose
        else:
            click.echo("The body pose feature is only available for full body didimos.", err=True)
            exit(1);
    
    if profile != None:
        payload["profile"] = profile

    if len(package_type) > 0:
        payload["transfer_formats"] = package_type

    for feature_item in feature:
        payload[feature_item] = 'true'

    depth = None

    if not ignore_cost:    
        # estimate how many points a generation will consume before they are consumed 
        # and prompt user to confirm operation before proceeding with the bulk request
        cost_estimation_api_path = "/v3/didimos-cost"
        cost_estimation_url = config.api_host + cost_estimation_api_path
        r = http_post_withphoto(cost_estimation_url, config.access_key, payload, batch_files[0], depth)

        json_response = r.json()
        is_error = r.json()['is_error'] if 'is_error' in json_response else False
        if is_error:
            click.echo("The requested configuration is invalid! Aborting...")
            exit(1);

        estimated_cost = r.json()['cost']

        total_estimated_cost = estimated_cost * len(batch_files)
        click.echo("The cost of each didimo generation is: "+str(estimated_cost))
        click.echo("The total cost of this bulk operation is: "+str(total_estimated_cost))
        
        click.confirm('Are you sure you want to proceed with the didimo creation?', abort=True)
        click.echo("Proceeding...")

    r = new_aux_shared_upload_core(config, url, input, depth, input, payload, output_display_type_json_flag)
    r_json = r
    if r_json['error'] == 1:
        upload_error_response = r
        if output_display_type_json_flag:
            click.secho("%s"%str(r_json), fg="red", err=True)
        else:
            click.secho('\nError %d uploading %s: \n%s' % (r.status_code, input, r.text), err=True, fg='red')
    else:
        if output_display_type_json_flag:
            click.secho("%s"%str(r_json), fg="blue", err=False)
        else:
            click.secho('\nCreated bulk from %s: \n%s' % (input, str(r_json)), err=False, fg='blue')


#####################################
#
# DIDIMO: get status, inspect, delete
#
######################################

@cli.command(short_help='Get status of didimos')
@click.help_option(*HELP_OPTION_NAMES)
@click.argument("id", required=True, nargs=-1)
@click.option('--output-display-type', help="Console output type.", 
                                       type=click.Choice(["human-readable", "json"]), 
                                       show_default=False)
@click.option("-s", "--silent", required=False, is_flag=True, default=False,
              help="Do not print anything. See help text for exit codes.")
@pass_api
def status(config, id, output_display_type, silent):
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

    output_display_type_json_flag = get_output_display_type_json_flag(config, output_display_type)

    didimos = []

    ids = create_set(id)

    # read didimo ids if used with a pipe
    if "-" in ids:
        ids = sys.stdin.readlines()

    try:

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
    except DidimoNotFoundException:
        click.secho('No didimo with the requested key was found on this account.', err=True, fg='red')
        sys.exit(0)

    if silent:
        sys.exit(0)

    if output_display_type_json_flag:
        click.echo(json.dumps(didimos, indent=4))
    else:
        print_status_header()
        for didimo in didimos:
            print_status_row(didimo)



@cli.command(short_help='Get details of didimos')
@click.help_option(*HELP_OPTION_NAMES)
@click.argument("id", required=True, nargs=-1)
#@click.option("-r", "--raw", required=False, is_flag=True, default=False,
#              help="Do not format output, print raw JSON response from API.")
@click.option('--output-display-type', help="Console output type.", 
                                       type=click.Choice(["human-readable", "json"]), 
                                       show_default=False)
@pass_api
def inspect(config, id, output_display_type):
    """
    Get details of didimos

    <ID> is the didimo ID to get information.

    Multiple didimo IDs are accepted, separated by a space or newline

    If <ID> is the character "-", read the IDs from STDIN.

    """

    output_display_type_json_flag = get_output_display_type_json_flag(config, output_display_type)

    didimos = []

    ids = create_set(id)

    # read didimo ids if used with a pipe
    if "-" in ids:
        ids = sys.stdin.readlines()

    try:
        for didimo in ids:
            response = get_didimo_status(config, didimo.rstrip())               

            # TODO
            # Remove this block when /status endpoint is consistent with /list
            if response['status_message'] != "":
                response["key"] = didimo.rstrip()
                response["status"] = "error"

            didimos.append(response)
    except DidimoNotFoundException:
        click.secho('No didimo with the requested key was found on this account.', err=True, fg='red')
        sys.exit(0)

    if output_display_type_json_flag:
        click.echo(json.dumps(didimos, indent=4))
    else:
        for didimo in didimos:
            click.secho("-- didimo "+response["key"]+" --", fg="green", err=True)
            print_key_value("Key", response["key"])
            print_key_value("Input type", response["input_type"])
            
            print_key_value("Cost", response["cost"])
            print_key_value("Created at", response["created_at"])
            print_key_value("Expires at", response["expires_at"])
            print_key_value("Status", response["status"])
            if response['status'] == "processing" or response['status'] == "error":
                print_key_value("Percent", response["percent"])
            if response['status_message'] != "":
                print_key_value("Status message", response["status_message"])
            print_key_value("Is favorite", response["is_favorite"])

            if "transfer_formats" in response:
                transfer_formats = []
                for trf in response["transfer_formats"]:
                    transfer_formats.append(trf["name"])
                print_key_value("Transfer formats", str(transfer_formats))

            if "meta_data" in response:
                click.secho("-- System Metadata --", fg="yellow", err=True)
                for meta_data in response["meta_data"]:
                    if meta_data["definer"] == "system":
                        print_key_value(meta_data["name"], meta_data["value"])
                click.secho("-- User-defined Metadata --", fg="blue", err=True)
                for meta_data in response["meta_data"]:
                    if meta_data["definer"] == "user":
                        print_key_value(meta_data["name"], meta_data["value"])
            click.secho("--------------------------------", fg="green", err=True)


@cli.command()
@click.help_option(*HELP_OPTION_NAMES)
@click.argument("id", required=True)
@click.option("-o", "--output", type=click.Path(),
              help="Output path. [default: <ID>.zip]")
@click.option('--package-type', '-p',
              type=click.Choice(["fbx", "gltf"]),
              help="Specify output type for this didimo.", show_default=True)
@click.option('--output-display-type', help="Console output type.", 
                                       type=click.Choice(["human-readable", "json"]), 
                                       show_default=False)
@pass_api
def download(config, id, output, package_type, output_display_type):
    """
    Download a didimo

    <ID> is the didimo ID.

    When given the "-" character, read the didimo
    ID from STDIN.
    """

    #output_display_type_json_flag = get_output_display_type_json_flag(config, output_display_type)

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
@click.argument("id", required=True)
@click.option('--output-display-type', help="Console output type.", 
                                       type=click.Choice(["human-readable", "json"]), 
                                       show_default=False)
@pass_api
def delete(config, id, output_display_type):
    """
    Delete a didimo

    <id> is the didimo key

    """
    
    output_display_type_json_flag = get_output_display_type_json_flag(config, output_display_type)

    api_path = "/v3/didimos/"
    url = config.api_host + api_path + id

    r = http_delete(url, auth=DidimoAuth(config, api_path))

    if output_display_type_json_flag:
        click.echo(r.text)
    else:
        if r.status_code != 204:
            if r.status_code == 404:
                click.secho('No didimo with the requested key was found on this account', err=True, fg='red')
            else:
                click.secho('Error %d' % r.status_code, err=True, fg='red')
            sys.exit(1)
        click.secho('Deleted!', err=False, fg='blue')


#####################################
#
# Hair/Asset Deformation
#
######################################

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
@click.option('--output-display-type', help="Console output type.", 
                                       type=click.Choice(["human-readable", "json"]), 
                                       show_default=False)
@pass_api
def hairsdeform(config, input, timeout, output_display_type):
    """
    Produce high fidelity hairstyle deformation for a didimo, given a deformation file

    <INPUT> is the deformation file (.dmx or .zip containing the DMX file).

    The CLI accepts a zip file containing a DMX file, extracting it, or the DMX file directly, 
    and sends it, along with the asset to deform, to the API. 
    
    The output package will be named with a suffix that represents the asset type (“_hairs”). 
    If the input was a zip file from which we are able to decode a didimo key, the output will be named after the original didimo key.

    """

    output_display_type_json_flag = get_output_display_type_json_flag(config, output_display_type)

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
        error_msg = "Error with path to dmx file"
        if output_display_type_json_flag:
            cmd_response_json = {
                                  "input_error": True,
                                  "message": error_msg
                                }
            click.echo(str(cmd_response_json))
        else:
            click.echo(error_msg)        
        return

    files = [('template_deformation', (filePath, open(
        filePath, 'rb'), 'application/octet-stream'))]

    headers = {
        'DIDIMO-API-KEY': config.access_key
    }

    r = requests.request("POST", url, headers=headers,
                         data=payload, files=files)

    deformation_aux_shared_processing_and_download(config, timeout, r, api_path, outputFileSuffix, output_display_type_json_flag)


@execute.command(short_help="Deform a model to match a didimo shape")
@click.help_option(*HELP_OPTION_NAMES)
@click.argument("vertex", required=True, type=click.Path(exists=True))
@click.argument("user_asset", required=True, type=click.Path(exists=True))
@click.option("-t", "--timeout", required=False, is_flag=False, default=None,
              help="Set maximum time allowed for the function to complete.")
@click.option('--output-display-type', help="Console output type.", 
                                       type=click.Choice(["human-readable", "json"]), 
                                       show_default=False)
@pass_api
def vertexdeform(config, vertex, user_asset, timeout, output_display_type):
    """
    Deform an asset to match a didimo shape

    <VERTEX> is the deformation file (.dmx or .zip containing the DMX file).
    <USER_ASSET> is the asset file to be deformed.

    The CLI accepts a zip file containing a DMX file, extracting it, or the DMX file directly, 
    and sends it, along with the asset to deform, to the API. 
    
    The output package will be named with a suffix that represents the asset type (“_vertexdeformation”). 
    If the vertex input was a zip file from which we are able to decode a didimo key, the output will be named after the original didimo key.

    """

    output_display_type_json_flag = get_output_display_type_json_flag(config, output_display_type)

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
        error_msg = "Error with path to dmx file"
        if output_display_type_json_flag:
            cmd_response_json = {
                                  "input_error": True,
                                  "message": error_msg
                                }
            click.echo(str(cmd_response_json))
        else:
            click.echo(error_msg)        
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
    
    deformation_aux_shared_processing_and_download(config, timeout, r, api_path, outputFileSuffix, output_display_type_json_flag)


#####################################
#
# Didimo Metadata
#
######################################

@cli.group()
@click.help_option(*HELP_OPTION_NAMES)
@pass_api
def metadata(config):
    """
    Perform metadata operations on didimos
    """
    pass

@metadata.command(short_help="Sets metadata on a didimo", name='set')
@click.help_option(*HELP_OPTION_NAMES)
@click.argument("id", required=True)
@click.argument("name", required=True)
@click.argument("value", required=True)
@click.option('--output-display-type', help="Console output type.", 
                                       type=click.Choice(["human-readable", "json"]), 
                                       show_default=False)
@pass_api
def set(config, id, name, value, output_display_type):
    """
    Sets metadata on a didimo

    <id> is the didimo key
    <name> is the metadata key
    <value> is the metadata value
    """
    output_display_type_json_flag = get_output_display_type_json_flag(config, output_display_type)

    api_path = "/v3/didimos/"+id+"/meta_data"
    url = config.api_host + api_path

    payload = {'name': name, 'value': value}
    
    r = http_post_no_break(url, auth=DidimoAuth(config, api_path), json=payload) 

    if output_display_type_json_flag:
        click.echo(r.text)
    else:
        if r.status_code != 201:
            if r.status_code == 404:
                click.secho('No didimo with the requested key was found on this account', err=True, fg='red')
            elif r.status_code == 400:
                click.secho('Please correct your input.', err=True, fg='red')
            else:
                click.secho('Error %d' % r.status_code, err=True, fg='red')
            sys.exit(1)
        click.secho('Metadata - Name: '+name+' Value: '+str(value), err=False, fg='blue')

@metadata.command(short_help="Gets metadata on a didimo", name='get')
@click.help_option(*HELP_OPTION_NAMES)
@click.argument("id", required=True)
@click.argument("name", required=True)
@click.option('--output-display-type', help="Console output type.", 
                                       type=click.Choice(["human-readable", "json"]), 
                                       show_default=False)
@pass_api
def get(config, id, name, output_display_type):
    """
    Retrieves metadata on a didimo

    <id> is the didimo key
    <name> is the metadata key
    """
    output_display_type_json_flag = get_output_display_type_json_flag(config, output_display_type)

    api_path = "/v3/didimos/"+id+"/meta_data/"+name
    url = config.api_host + api_path

    
    r = http_get(url, auth=DidimoAuth(config, api_path)) 

    if output_display_type_json_flag:
        click.echo(r.text)
    else:
        if r.status_code != 200:
            if r.status_code == 404:
                res = r.json()
                if res["code"] == 10008:
                    click.secho('Metadata attribute not found for this didimo.', err=True, fg='red')
                else:
                    click.secho('No didimo with the requested key was found on this account.', err=True, fg='red')
            elif r.status_code == 400:
                click.secho('Please correct your input.', err=True, fg='red')
            else:
                click.secho('Error %d' % r.status_code, err=True, fg='red')
            sys.exit(1)

        response = r.json()
        click.secho('Metadata - Name: '+name+' Value: '+str(response['value']), err=False, fg='blue')

@metadata.command(short_help="Updates metadata on a didimo", name='update')
@click.help_option(*HELP_OPTION_NAMES)
@click.argument("id", required=True)
@click.argument("name", required=True)
@click.argument("value", required=True)
@click.option('--output-display-type', help="Console output type.", 
                                       type=click.Choice(["human-readable", "json"]), 
                                       show_default=False)
@pass_api
def update(config, id, name, value, output_display_type):
    """
    Updates metadata on a didimo

    <id> is the didimo key
    <name> is the metadata key
    <value> is the new metadata value
    """
    output_display_type_json_flag = get_output_display_type_json_flag(config, output_display_type)

    api_path = "/v3/didimos/"+id+"/meta_data/"+name
    url = config.api_host + api_path

    payload = {'name': name, 'value': value}
    
    r = http_put(url, auth=DidimoAuth(config, api_path), json=payload) 

    if output_display_type_json_flag:
        click.echo(r.text)
    else:
        if r.status_code != 200:
            if r.status_code == 404:
                res = r.json()
                if res["code"] == 10008:
                    click.secho('Metadata attribute not found for this didimo.', err=True, fg='red')
                else:
                    click.secho('No didimo with the requested key was found on this account.', err=True, fg='red')
            elif r.status_code == 403:
                click.secho('The didimo\'s metadata item cannot be updated because it is not user-defined.', err=True, fg='red')
            elif r.status_code == 400:
                click.secho('Please correct your input.', err=True, fg='red')
            else:
                click.secho('Error %d' % r.status_code, err=True, fg='red')
            sys.exit(1)
        click.secho('Updated!', err=False, fg='blue')


@metadata.command(short_help="Deletes metadata on a didimo", name='delete')
@click.help_option(*HELP_OPTION_NAMES)
@click.argument("id", required=True)
@click.argument("name", required=True)
@click.option('--output-display-type', help="Console output type.", 
                                       type=click.Choice(["human-readable", "json"]), 
                                       show_default=False)
@pass_api
def delete(config, id, name, output_display_type):
    """
    Deletes metadata on a didimo

    <id> is the didimo key
    <name> is the metadata key
    """
    output_display_type_json_flag = get_output_display_type_json_flag(config, output_display_type)

    api_path = "/v3/didimos/"+id+"/meta_data/"+name
    url = config.api_host + api_path
    
    r = http_delete(url, auth=DidimoAuth(config, api_path)) 

    if output_display_type_json_flag:
        click.echo(r.text)
    else:
        if r.status_code != 204:
            if r.status_code == 404:
                res = r.json()
                if res["code"] == 10008:
                    click.secho('Metadata attribute not found for this didimo.', err=True, fg='red')
                else:
                    click.secho('No didimo with the requested key was found on this account.', err=True, fg='red')
            elif r.status_code == 403:
                click.secho('The didimo\'s metadata item cannot be deleted because it is not user-defined.', err=True, fg='red')
            elif r.status_code == 400:
                click.secho('Please correct your input.', err=True, fg='red')
            else:
                click.secho('Error %d' % r.status_code, err=True, fg='red')
            sys.exit(1)
        click.secho('Deleted!', err=False, fg='blue')

#####################################
#
# Didimo Generation Templates
#
######################################

@cli.group()
@click.help_option(*HELP_OPTION_NAMES)
@pass_api
def generation_template(config):
    """
    Perform didimo generation template management operations on general compatibility DGP version
    """
    pass

@cli.group()
@click.help_option(*HELP_OPTION_NAMES)
@pass_api
def generation_template_2_5_7(config):
    """
    Perform didimo generation template management operations on DGP compatible version 2.5.7
    """
    pass

@cli.group()
@click.help_option(*HELP_OPTION_NAMES)
@pass_api
def generation_template_2_5_10(config):
    """
    Perform didimo generation template management operations on DGP compatible version 2.5.10
    """
    pass

## LIST ##########

@generation_template_2_5_7.command(short_help="Lists available didimo generation templates", name='list')
@click.help_option(*HELP_OPTION_NAMES)
@click.option('--output-display-type', help="Console output type.", 
                                       type=click.Choice(["human-readable", "json"]), 
                                       show_default=False)
@pass_api
def list(config, output_display_type):
    """
    Lists available didimo generation templates
    """
    list_didimo_generation_templates_aux(config, output_display_type)

@generation_template_2_5_10.command(short_help="Lists available didimo generation templates", name='list')
@click.help_option(*HELP_OPTION_NAMES)
@click.option('--output-display-type', help="Console output type.", 
                                       type=click.Choice(["human-readable", "json"]), 
                                       show_default=False)
@pass_api
def list(config, output_display_type):
    """
    Lists available didimo generation templates
    """
    list_didimo_generation_templates_aux(config, output_display_type)


def list_didimo_generation_templates_aux(config, output_display_type):
    """
    (Shared Implementation) Lists available didimo generation templates
    """

    output_display_type_json_flag = get_output_display_type_json_flag(config, output_display_type)

    api_path = "/v3/didimo_generation_templates"
    url = config.api_host + api_path

    
    r = http_get(url, auth=DidimoAuth(config, api_path)) 

    if output_display_type_json_flag:
        click.echo(r.text)
    else:
        if r.status_code != 200:
            if r.status_code == 404:
                res = r.json()
                click.secho('Not found.', err=True, fg='red')
            elif r.status_code == 400:
                click.secho('Please correct your input.', err=True, fg='red')
            else:
                click.secho('Error %d' % r.status_code, err=True, fg='red')
            sys.exit(1)

        while True:

            json_response = r.json()
            _DGTs = json_response['didimo_generation_templates']
            next_page = json_response['__links']['next'] if '__links' in json_response and 'next' in json_response['__links'] else None

            print_didimo_generation_template_header()
            for _DGT in _DGTs:
                print_didimo_generation_template_row(_DGT)

            if next_page != None:
                click.confirm('There are more results. Fetch next page?', abort=True)

                api_path = next_page
                url = api_path
                r = http_get(url, auth=DidimoAuth(config, api_path))
            else:
                break

## GET ##########

@generation_template_2_5_7.command(short_help="Gets a didimo generation template", name='get')
@click.help_option(*HELP_OPTION_NAMES)
@click.argument("uuid", required=True)
@click.option('--output-display-type', help="Console output type.", 
                                       type=click.Choice(["human-readable", "json"]), 
                                       show_default=False)
@pass_api
def get(config, uuid, output_display_type):
    """
    Retrieves a didimo generation template

    <uuid> is the didimo generation template UUID
    """
    get_didimo_generation_template_aux(config, uuid, output_display_type)

@generation_template_2_5_10.command(short_help="Gets a didimo generation template", name='get')
@click.help_option(*HELP_OPTION_NAMES)
@click.argument("uuid", required=True)
@click.option('--output-display-type', help="Console output type.", 
                                       type=click.Choice(["human-readable", "json"]), 
                                       show_default=False)
@pass_api
def get(config, uuid, output_display_type):
    """
    Retrieves a didimo generation template

    <uuid> is the didimo generation template UUID
    """
    get_didimo_generation_template_aux(config, uuid, output_display_type)

## DELETE ##########

@generation_template_2_5_7.command(short_help="Deletes a didimo generation template", name='delete')
@click.help_option(*HELP_OPTION_NAMES)
@click.argument("uuid", required=True)
@click.option('--output-display-type', help="Console output type.", 
                                       type=click.Choice(["human-readable", "json"]), 
                                       show_default=False)
@pass_api
def delete(config, uuid, output_display_type):
    """
    Deletes a didimo generation template

    <id> is the didimo generation template UUID
    """
    delete_didimo_generation_template_aux(config, uuid, output_display_type)

@generation_template_2_5_10.command(short_help="Deletes a didimo generation template", name='delete')
@click.help_option(*HELP_OPTION_NAMES)
@click.argument("uuid", required=True)
@click.option('--output-display-type', help="Console output type.", 
                                       type=click.Choice(["human-readable", "json"]), 
                                       show_default=False)
@pass_api
def delete(config, uuid, output_display_type):
    """
    Deletes a didimo generation template

    <id> is the didimo generation template UUID
    """
    delete_didimo_generation_template_aux(config, uuid, output_display_type)


## CREATE ##########

@generation_template_2_5_7.command(short_help="Create a didimo generation template", name='create')
@click.help_option(*HELP_OPTION_NAMES)
@click.argument("template_name", required=True)
@click.argument("description", required=True)
@click.argument("input_type", type=click.Choice(["photo", "rgbd"]), required=True, metavar="TYPE")
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
                  ["female", "male", "auto"]),
              help="Create didimo with gender option. This option is only available for full-body didimos.")
@click.option('--package-type', '-p', multiple=True,
              type=click.Choice(["fbx", "gltf"]),
              help="Specify output types for this didimo. This flag can be used multiple times.", show_default=True)
@click.option('--output-display-type', help="Console output type.", 
                                       type=click.Choice(["human-readable", "json"]), 
                                       show_default=False)
@pass_api
def create(config, template_name, description, input_type, feature, avatar_structure, garment, gender, max_texture_dimension, package_type, output_display_type):
    """
    Create a didimo generation template on DGP compatible version 2.5.7

    TEMPLATE_NAME is the didimo generation template name.\n
    DESCRIPTION is the didimo generation template description.\n

    TYPE is the type of input used to create the didimo. Accepted values are:

    \b
        - photo (input must be a .jpg/.jpeg/.png)
        - rgbd (input must be a .jpg/.jpeg/.png; use -d to provide the depth file, which must be a .png)

        For more information on the input types, visit
        https://developer.didimo.co/docs/cli\b
    \b
    Examples:
        Create a template named xpto that generates a didimo from a photo
        $ didimo generation-template create xpto "simple template example based on photo input" photo
    """
    output_display_type_json_flag = get_output_display_type_json_flag(config, output_display_type)

    settings = {}

    if input_type != None:
        settings["input_type"] = input_type

    if avatar_structure != None:
        settings["avatar_structure"] = avatar_structure
    
    if garment != None:
        settings["garment"] = garment

    if gender != None:
        settings["gender"] = gender

    if max_texture_dimension != None:
        settings["max_texture_dimension"] = max_texture_dimension

    if len(package_type) > 0:
        settings["transfer_formats"] = package_type

    for feature_item in feature:
        settings[feature_item] = 'true'

    payload = {
        "template_name": template_name,
        "description": description,
        "settings": settings,
        "scope": "user"
    }
    serialized_payload = str(payload)

    api_path = "/v3/didimo_generation_templates"
    url = config.api_host + api_path

    r = http_request_json(url, "POST", config.access_key, serialized_payload, False)
    generation_template_shared_response_processing(r, output_display_type_json_flag)


@generation_template_2_5_10.command(short_help="Create a didimo generation template", name='create')
@click.help_option(*HELP_OPTION_NAMES)
@click.argument("template_name", required=True)
@click.argument("description", required=True)
@click.argument("input_type", type=click.Choice(["photo", "rgbd"]), required=True, metavar="TYPE")
@click.option('--feature', '-f', multiple=True,
              type=click.Choice(
                  ["oculus_lipsync", "simple_poses", "arkit", "aws_polly"]),
              help="Create didimo with optional features. This flag can be used multiple times.")
@click.option('--avatar-structure', multiple=False,
              type=click.Choice(
                  ["head-only", "full-body"]),
              help="Create didimo with avatar structure option.")
@click.option('--garment', multiple=False,
              type=click.Choice(
                  ["none","casual", "sporty", "business"]),
              help="Create didimo with garment option. This option is only available for full-body didimos.")
@click.option('--gender', multiple=False,
              type=click.Choice(
                  ["female", "male", "auto"]),
              help="Create didimo with gender option. This option is only available for full-body didimos.")
@click.option('--hair', multiple=False,
              type=click.Choice(
                  ["baseball_cap", 
                  "hair_001",  
                  "hair_002", 
                  "hair_003", 
                  "hair_004", 
                  "hair_005", 
                  "hair_006", 
                  "hair_007", 
                  "hair_008", 
                  "hair_009", 
                  "hair_010", 
                  "hair_011"]),
              help="Create didimo with hair option.")
@click.option('--body-pose', '-bp',
              type=click.Choice(["A", "T"]),
              help="Specify body pose for this didimo. This option is only available for full-body didimos.", show_default=False)
@click.option('--profile', 
              type=click.Choice(["standard", "optimized"]),
              help="Specify a profile to drive this didimo generation.", show_default=False)
@click.option('--package-type', '-p', multiple=True,
              type=click.Choice(["fbx", "gltf"]),
              help="Specify output types for this didimo. This flag can be used multiple times.", show_default=True)
@click.option('--output-display-type', help="Console output type.", 
                                       type=click.Choice(["human-readable", "json"]), 
                                       show_default=False)
@pass_api
def create(config, template_name, description, input_type, feature, avatar_structure, garment, gender, hair, body_pose, profile, package_type, output_display_type):
    """
    Create a didimo generation template on DGP compatible version 2.5.10

    TEMPLATE_NAME is the didimo generation template name.\n
    DESCRIPTION is the didimo generation template description.\n

    TYPE is the type of input used to create the didimo. Accepted values are:

    \b
        - photo (input must be a .jpg/.jpeg/.png)
        - rgbd (input must be a .jpg/.jpeg/.png; use -d to provide the depth file, which must be a .png)

        For more information on the input types, visit
        https://developer.didimo.co/docs/cli\b

    \b
    Examples:
        Create a template named xpto that generates a didimo from a photo
        $ didimo generation-template create xpto "simple template example based on photo input" photo
    """
    output_display_type_json_flag = get_output_display_type_json_flag(config, output_display_type)

    settings = {}

    if input_type != None:
        settings["input_type"] = input_type

    if avatar_structure != None:
        settings["avatar_structure"] = avatar_structure
    
    if garment != None:
        settings["garment"] = garment

    if gender != None:
        settings["gender"] = gender

    if hair != None:
        settings["hair"] = hair

    if body_pose != None:
        if avatar_structure == "full-body":
            settings["body_pose"] = body_pose
        else:
            click.echo("The body pose feature is only available for full body didimos.", err=True)
            exit(1);
    
    if profile != None:
        settings["profile"] = profile

    if len(package_type) > 0:
        settings["transfer_formats"] = package_type

    for feature_item in feature:
        settings[feature_item] = 'true'

    payload = {
        "template_name": template_name,
        "description": description,
        "settings": settings,
        "scope": "user"
    }
    serialized_payload = str(payload)

    api_path = "/v3/didimo_generation_templates"

    print(serialized_payload)
    url = config.api_host + api_path

    r = http_request_json(url, "POST", config.access_key, serialized_payload, False)
    generation_template_shared_response_processing(r, output_display_type_json_flag)


## UPDATE ##########

@generation_template_2_5_7.command(short_help="Updates a didimo generation template", name='update')
@click.help_option(*HELP_OPTION_NAMES)
@click.argument("uuid", required=True)
@click.argument("template_name", required=True)
@click.argument("description", required=True)
@click.argument("input_type", type=click.Choice(["photo", "rgbd"]), required=True, metavar="TYPE")
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
                  ["female", "male", "auto"]),
              help="Create didimo with gender option. This option is only available for full-body didimos.")
@click.option('--package-type', '-p', multiple=True,
              type=click.Choice(["fbx", "gltf"]),
              help="Specify output types for this didimo. This flag can be used multiple times.", show_default=True)
@click.option('--output-display-type', help="Console output type.", 
                                       type=click.Choice(["human-readable", "json"]), 
                                       show_default=False)
@pass_api
def update(config, uuid, template_name, description, input_type, feature, avatar_structure, garment, gender, max_texture_dimension, package_type, output_display_type):
    """
    Update a didimo generation template on DGP compatible version 2.5.7

    UUID is the didimo generation template UUID.\n
    TEMPLATE_NAME is the didimo generation template name.\n
    DESCRIPTION is the didimo generation template description.\n

    TYPE is the type of input used to create the didimo. Accepted values are:

    \b
        - photo (input must be a .jpg/.jpeg/.png)
        - rgbd (input must be a .jpg/.jpeg/.png; use -d to provide the depth file, which must be a .png)

        For more information on the input types, visit
        https://developer.didimo.co/docs/cli\b
    \b
    Examples:
        Updates a template with UUID xyz, by renaming it to "simple photo template" and matching description with settings that generates a didimo from a photo
        $ didimo generation-template update xyz "simple photo template" "simple template example based on photo input" photo /path/input.jpg
    """
    output_display_type_json_flag = get_output_display_type_json_flag(config, output_display_type)

    settings = {}

    if input_type != None:
        settings["input_type"] = input_type

    if avatar_structure != None:
        settings["avatar_structure"] = avatar_structure
    
    if garment != None:
        settings["garment"] = garment

    if gender != None:
        settings["gender"] = gender

    if max_texture_dimension != None:
        settings["max_texture_dimension"] = max_texture_dimension

    if len(package_type) > 0:
        settings["transfer_formats"] = package_type

    for feature_item in feature:
        settings[feature_item] = 'true'

    payload = {
        "template_name": template_name,
        "description": description,
        "settings": settings
    }
    serialized_payload = str(payload)

    api_path = "/v3/didimo_generation_templates/"+uuid
    url = config.api_host + api_path

    r = http_request_json(url, "PUT", config.access_key, serialized_payload, False)
    generation_template_shared_response_processing(r, output_display_type_json_flag)


@generation_template_2_5_10.command(short_help="Updates a didimo", name='update')
@click.help_option(*HELP_OPTION_NAMES)
@click.argument("uuid", required=True)
@click.argument("template_name", required=True)
@click.argument("description", required=True)
@click.argument("input_type", type=click.Choice(["photo", "rgbd"]), required=True, metavar="TYPE")
@click.option('--feature', '-f', multiple=True,
              type=click.Choice(
                  ["oculus_lipsync", "simple_poses", "arkit", "aws_polly"]),
              help="Create didimo with optional features. This flag can be used multiple times.")
@click.option('--avatar-structure', multiple=False,
              type=click.Choice(
                  ["head-only", "full-body"]),
              help="Create didimo with avatar structure option.")
@click.option('--garment', multiple=False,
              type=click.Choice(
                  ["none","casual", "sporty", "business"]),
              help="Create didimo with garment option. This option is only available for full-body didimos.")
@click.option('--gender', multiple=False,
              type=click.Choice(
                  ["female", "male", "auto"]),
              help="Create didimo with gender option. This option is only available for full-body didimos.")
@click.option('--hair', multiple=False,
              type=click.Choice(
                  ["baseball_cap", 
                  "hair_001",  
                  "hair_002", 
                  "hair_003", 
                  "hair_004", 
                  "hair_005", 
                  "hair_006", 
                  "hair_007", 
                  "hair_008", 
                  "hair_009", 
                  "hair_010", 
                  "hair_011"]),
              help="Create didimo with hair option.")
@click.option('--body-pose', '-bp',
              type=click.Choice(["A", "T"]),
              help="Specify body pose for this didimo. This option is only available for full-body didimos.", show_default=False)
@click.option('--profile',
              type=click.Choice(["standard", "optimized"]),
              help="Specify a profile to drive this didimo generation.", show_default=False)
@click.option('--package-type', '-p', multiple=True,
              type=click.Choice(["fbx", "gltf"]),
              help="Specify output types for this didimo. This flag can be used multiple times.", show_default=True)
@click.option('--output-display-type', help="Console output type.", 
                                       type=click.Choice(["human-readable", "json"]), 
                                       show_default=False)
@pass_api
def update(config, uuid, template_name, description, input_type, feature, avatar_structure, garment, gender, hair, body_pose, profile, package_type, output_display_type):
    """
    Update a didimo generation template on DGP compatible version 2.5.10

    UUID is the didimo generation template UUID.\n
    TEMPLATE_NAME is the didimo generation template name.\n
    DESCRIPTION is the didimo generation template description.\n

    TYPE is the type of input used to create the didimo. Accepted values are:

    \b
        - photo (input must be a .jpg/.jpeg/.png)
        - rgbd (input must be a .jpg/.jpeg/.png; use -d to provide the depth file, which must be a .png)

        For more information on the input types, visit
        https://developer.didimo.co/docs/cli\b
    \b
    Examples:
        Updates a template with UUID xyz, by renaming it to "simple photo template" and matching description with settings that generates a didimo from a photo
        $ didimo generation-template update xyz "simple photo template" "simple template example based on photo input" photo
    """
    output_display_type_json_flag = get_output_display_type_json_flag(config, output_display_type)

    settings = {}

    if input_type != None:
        settings["input_type"] = input_type

    if avatar_structure != None:
        settings["avatar_structure"] = avatar_structure
    
    if garment != None:
        settings["garment"] = garment

    if gender != None:
        settings["gender"] = gender

    if hair != None:
        settings["hair"] = hair

    if body_pose != None:
        if avatar_structure == "full-body":
            settings["body_pose"] = body_pose
        else:
            click.echo("The body pose feature is only available for full body didimos.", err=True)
            exit(1);
    
    if profile != None:
        settings["profile"] = profile

    if len(package_type) > 0:
        settings["transfer_formats"] = package_type

    for feature_item in feature:
        settings[feature_item] = 'true'

    payload = {
        "template_name": template_name,
        "description": description,
        "settings": settings
    }
    serialized_payload = str(payload)

    api_path = "/v3/didimo_generation_templates/"+uuid
    url = config.api_host + api_path

    r = http_request_json(url, "PUT", config.access_key, serialized_payload, False)
    generation_template_shared_response_processing(r, output_display_type_json_flag)


#####################################
#
# Other useful commands and functions
#
######################################

@cli.command()
@click.help_option(*HELP_OPTION_NAMES)
@click.option('--output-display-type', help="Console output type.", 
                                       type=click.Choice(["human-readable", "json"]), 
                                       show_default=False)
@pass_api
def version(config, output_display_type):
    """
    Print CLI version and exit
    """
    output_display_type_json_flag = get_output_display_type_json_flag(config, output_display_type)

    if output_display_type_json_flag:
        click.echo({"cli_version":__version__})
    else:
        click.echo("CLI version: "+__version__)
    sys.exit(0)


def get_api_version(config, output_display_type = "ignore_display_rules"):

    output_display_type_json_flag = get_output_display_type_json_flag(config, output_display_type)

    # Get the current DGP version from the applications using the selected API Key
    api_path = "/v3/accounts/default/applications"
    url = config.api_host + api_path

    #r = http_get(url, auth=DidimoAuth(config, api_path))
    r = cache_this_call(url, config.access_key, auth=DidimoAuth(config, api_path)) 


    if output_display_type_json_flag:
        click.echo(r.text)
    else:
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


@cli.command()
@click.help_option(*HELP_OPTION_NAMES)
@click.option('--output-display-type', help="Console output type.", 
                                       type=click.Choice(["human-readable", "json"]), 
                                       show_default=False)
@pass_api
def version_api(config, output_display_type):
    """
    Print API/DGP version and exit
    """
    output_display_type_json_flag = get_output_display_type_json_flag(config, output_display_type)

    if output_display_type_json_flag:
        click.echo({"api_version":get_api_version(config, "ignore_display_rules")})
    else:
        print("API version: "+get_api_version(config, output_display_type))
    sys.exit(0)

#@cli.command()
#@click.help_option(*HELP_OPTION_NAMES)
#@click.option('--output-display-type', help="Console output type.", 
#                                       type=click.Choice(["human-readable", "json"]), 
#                                       show_default=False)
#@pass_api
def version_cli_compatibility_rules(config, output_display_type):
    """
    Print CLI/DGP version compatibility rules and exit
    """
    print("CLI version - compatibility rules: "+str(get_cli_version_compatibility_rules(config, output_display_type)))
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

