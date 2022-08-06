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

from .utils import print_key_value, print_status_header, print_status_row
from .network import DidimoAuth, http_get, http_post, http_post_withphoto, http_post_no_break, http_put, http_delete, cache_this_call, clear_network_cache
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


def list_aux(config, api_path, page_size, index, navigate, sort_by, sort_order, raw):
    """
    List didimos
    """

    url = config.api_host + api_path

    url = url + "?page="+str(index)

    if page_size != None:
        url = url + "&page_size="+str(page_size)

    sort_order_api = "-"
    if sort_order != None:
        if sort_order == "asc" or sort_order == "ascending":
            sort_order_api = "+"
        elif sort_order == "desc" or sort_order == "descending":
            sort_order_api = "-"
        else:
            click.secho("Unknown sort order! Please correct the input. ", fg='red', err=True)
            exit(1);

    if sort_by != None:
        url = url + "&order_by="+sort_order_api+sort_by

    r = http_get(url, auth=DidimoAuth(config, api_path))
    json_response = r.json()
    #print(str(json_response))
    is_error = r.json()['is_error'] if 'is_error' in json_response else False
    if is_error:
        click.echo("An error has occurred! Aborting...")
        exit(1);

    if raw:
        click.echo(r.text)
    else:

        if index < 1:
            sys.exit(0)

        didimos = []
        next_page = json_response['__links']['next'] if '__links' in json_response and 'next' in json_response['__links'] else None
        page = index
        didimos += r.json()['didimos']

        while True:

            while page != index:

                if next_page != None:
                    api_path = next_page
                    url = api_path
                    r = http_get(url, auth=DidimoAuth(config, api_path))
                    json_response = r.json()
                    didimos += json_response['didimos']
                    next_page = json_response['__links']['next'] if '__links' in json_response else None
                    page += 1
                else:
                    break

            print_status_header()
            for didimo in didimos:
                print_status_row(didimo)

            if navigate and next_page != None:
                click.confirm('There are more results. Fetch next page?', abort=True)
                index = index + 1
                didimos = []
            else:
                break

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
@click.option("-r", "--raw", required=False, is_flag=True, default=False,
              help="Do not format output, print raw JSON response from API.")
@pass_api
def list(config, page_size, index, navigate, sort_by, sort_order, raw):
    """
    List didimos
    """
    api_path = "/v3/didimos/"
    list_aux(config, api_path, page_size, index, navigate, sort_by, sort_order, raw)

@cli.command()
@click.help_option(*HELP_OPTION_NAMES)
@click.option("-n", "--number", required=False, default=1, show_default=True,
              help="Number of pages to query from the API. Each page has 10 didimos.")
@click.option("-r", "--raw", required=False, is_flag=True, default=False,
              help="Do not format output, print raw JSON response from API, ignoring --number.")
@pass_api
def list_demo_didimos(config, number, raw):
    """
    List demo didimos
    """
    api_path = "/v3/didimos/demos"
    list_aux(config, api_path, 10, number, False, "created_at", "descending", raw)


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

@cli.command(short_help="Create a didimo")
@pass_api
def new(config):
    """
    Create a didimo
    """
    pass #this is a dummy function just to show up on the main menu



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
              type=click.Choice(["2.5.2"]),
              default="2.5.2",
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

    INPUT is the path to the input file. It can also be a zip file or a folder containing multiple photos (all files will be treated as input photos).

    \b
    Examples:
        Create a didimo from a photo
        $ didimo new photo /path/input.jpg

    """

    batch_files = new_aux_shared_preprocess_batch_files(input, input_type)

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
        if batch_files != None:
            #print(batch_files[0])
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

    new_aux_shared_upload_processing_and_download(config, url, batch_files, depth, payload, no_wait, no_download, output,batch_flag)


def new_aux_shared_preprocess_batch_files(input, input_type):
    """
    Shared code that handles preprocessing batch files (zip or directory) from the provided input
    """
    batch_flag = False
    batch_processing_path = None
    batch_total_files = 0
    temp_batch_files = None
    batch_files = []

    #if (input end with zip or /):
    if input.endswith('.zip') or os.path.isdir(input):
        if input_type != "photo":
            click.echo("Batch processing is only available for the photo input type. Please correct the command and try again.")
            return None
        #if ignore_cost != True:
        #    echo("Batch processing does not support didimo cost verification. Please use the --ignore-cost option and try again.")
        #    return
        else:
            batch_flag = True
            separator = "/"
            if platform.system() == "Windows":
                separator = "\\"
            #TODO: uncompress zip to temp and read directory, or read directory, according to given input being zip or folder
            if input.endswith('.zip'):
                temp_directory_to_extract_to = "temp"
                path_prefix = temp_directory_to_extract_to
  
                directory = os.getcwd()
                if not directory.endswith(separator):
                    directory = directory + separator
                batch_processing_path = directory+temp_directory_to_extract_to 
                shutil.rmtree(temp_directory_to_extract_to, ignore_errors=True)
                with zipfile.ZipFile(input, 'r') as zip_ref:
                    zip_ref.extractall(temp_directory_to_extract_to)
                    zip_ref.close()
            elif os.path.isdir(input):
                batch_processing_path = input
                path_prefix = input
            else:
                click.echo("file not supported")
                return None
            temp_batch_files=os.listdir(batch_processing_path)
            #batch_total_files = len(fnmatch.filter(batch_files, '*.*'))
            #click.echo("Batch processing - path: " + batch_processing_path)
            #click.echo("Batch processing - files count: " + str(batch_total_files))

            if not path_prefix.endswith(separator):
                path_prefix = path_prefix + separator
            for idx, input_file in enumerate(temp_batch_files):
                #print(input_file)
                if input_file != ".DS_Store" and not os.path.isdir(path_prefix + input_file):
                    batch_files.append(path_prefix + input_file)
                    print(path_prefix + input_file)

            batch_total_files = len(fnmatch.filter(batch_files, '*.*'))
            click.echo("Batch processing - files count: " + str(batch_total_files))

            return batch_files
    else:
        return None

def new_aux_shared_upload_processing_and_download(config, url, batch_files, depth, payload, no_wait, no_download, output, batch_flag):
    """
    Shared code that handles polling status and managing download
    """
    
    batch_didimo_ids = []
    #click.echo("Uploading files...")
    with click.progressbar(length=len(batch_files), label='Uploading files...', show_eta=False) as bar:
                    last_value = 0
                    i = 0
                    
                    for input_file in batch_files:
                        r = http_post_withphoto(url, config.access_key, payload, input_file, depth, False)

                        if r.status_code != 200 and r.status_code != 201:
                            click.secho('\nError %d uploading %s: %s' % (r.status_code, input_file, r.text), err=True, fg='red')
                            didimo_id = None
                        else:
                            didimo_id = r.json()['key']

                        batch_didimo_ids.append(didimo_id)
                        i = i + 1

                        update = i - last_value
                        last_value = i
                        bar.update(update)

                        #click.echo(""+str(i)+"/"+str(len(batch_files)))

    click.echo("Checking progress...")
    complete_tasks = MyQueue()
    jobs = []
    i = 0
    for input_file in batch_files:

        if not no_wait:

            didimo_id = batch_didimo_ids[i]
            i = i + 1

            if didimo_id == None:
                continue

            if batch_flag: #fork and don't output progress bars

                no_error = None
                with click.progressbar(length=100, label='Creating didimo '+didimo_id, show_eta=False) as bar:
                    last_value = 0
                    initing_progress_bar = True
                    while True:
                        if not initing_progress_bar:
                            response = get_didimo_status(config, didimo_id)
                            #click.echo(response)
                            #click.echo("Didimo "+didimo_id+": "+str(response['percent'])+"")
                            percent = response.get('percent', 100)
                            update = percent - last_value
                            last_value = percent
                            bar.update(update)
                            if response['status_message'] != "":
                                no_error = False
                                click.secho(err=True)
                                click.secho('Error generating didimo %s from %s: %s' % (didimo_id, str(input_file), response["status_message"]), err=True, fg='red')
                                break
                            if response['status'] == 'done':
                                no_error = True
                                break
                        else:
                            bar.update(0)
                            initing_progress_bar = False
                        time.sleep(2)
                        
                if not no_download and no_error == True:

                    #click.echo("Downloading didimo "+didimo_id+"...")

                    if output is None:
                        output = ""
                    elif output != "":
                        if not output.endswith('/'):
                            output = output + "/"

                    while True:
                        active_child_count = len(jobs)-complete_tasks.qsize()
                        if active_child_count < 5:
                            p = multiprocessing.Process(target=download_didimo_subprocess, args=(config, didimo_id, "", output, False,complete_tasks,))
                            jobs.append(p)
                            p.start()
                            break
                        else:
                            #click.echo("Waiting to download | Jobs:"+str(len(jobs))+" | Active processes:"+str(active_child_count)+" | Completed:"+str(complete_tasks.qsize()))
                            time.sleep(1)
                    
            else:
                with click.progressbar(length=100, label='Creating didimo '+didimo_id, show_eta=False) as bar:
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

    #check if child processes are still running and wait for them to finish
    if batch_flag:
        click.echo("Please wait while the remaining files are finished downloading...")
        for job in jobs:
            job.join()
    click.echo("All done!")

def download_didimo_subprocess(config, didimo_id, package_type, output, showProgressBar, complete_tasks):
    download_didimo(config, didimo_id, package_type, output, showProgressBar)
    complete_tasks.put(didimo_id + ' is done by ' + current_process().name)


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
@click.option("--version", "-v",
              type=click.Choice(["2.5.7"]),
              default="2.5.7",
              help="Version of the didimo.", show_default=True)
@pass_api
def new_2_5_7(config, input_type, input, depth, feature, avatar_structure, garment, gender, max_texture_dimension, no_download, no_wait, output, package_type, ignore_cost, version):
    """
    Create a didimo

    TYPE is the type of input used to create the didimo. Accepted values are:

    \b
        - photo (input must be a .jpg/.jpeg/.png)
        - rgbd (input must be a .jpg/.jpeg/.png; use -d to provide the depth file, which must be a .png)

        For more information on the input types, visit
        https://developer.didimo.co/docs/cli\b

    INPUT is the path to the input file (which must be a .jpg/.jpeg/.png/.zip or a directory containing photos)

    \b
    Examples:
        Create a didimo from a photo
        $ didimo new photo /path/input.jpg

    """

    batch_files = new_aux_shared_preprocess_batch_files(input, input_type)

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

    new_aux_shared_upload_processing_and_download(config, url, batch_files, depth, payload, no_wait, no_download, output,batch_flag)


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
@click.option('--profile', default="standard",
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
@click.option("--version", "-v",
              type=click.Choice(["2.5.10"]),
              default="2.5.10",
              help="Version of the didimo.", show_default=True)
@pass_api
def new_2_5_10(config, input_type, input, depth, feature, avatar_structure, garment, gender, hair, body_pose, profile, no_download, no_wait, output, package_type, ignore_cost, version):
    """
    Create a didimo

    TYPE is the type of input used to create the didimo. Accepted values are:

    \b
        - photo (input must be a .jpg/.jpeg/.png)
        - rgbd (input must be a .jpg/.jpeg/.png; use -d to provide the depth file, which must be a .png)

        For more information on the input types, visit
        https://developer.didimo.co/docs/cli\b

    INPUT is the path to the input file (which must be a .jpg/.jpeg/.png/.zip or a directory containing photos)

    \b
    Examples:
        Create a didimo from a photo
        $ didimo new photo /path/input.jpg

    """

    batch_files = new_aux_shared_preprocess_batch_files(input, input_type)

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
        package_type = package_type[0]
    else:
        package_type = "gltf"

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

    new_aux_shared_upload_processing_and_download(config, url, batch_files, depth, payload, no_wait, no_download, output,batch_flag)



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

    batch_files = new_aux_shared_preprocess_batch_files(input, input_type)

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
        if batch_files != None:
            r = http_post_withphoto(url+"-cost", config.access_key, payload, batch_files[0], depth, False)
        else:
            r = http_post_withphoto(url+"-cost", config.access_key, payload, input, depth, False)

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

    new_aux_shared_upload_processing_and_download(config, url, batch_files, depth, payload, no_wait, no_download, output,batch_flag)


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


@cli.command(short_help='Get details of didimos')
@click.help_option(*HELP_OPTION_NAMES)
@click.argument("id", required=True, nargs=-1)
@click.option("-r", "--raw", required=False, is_flag=True, default=False,
              help="Do not format output, print raw JSON response from API.")
@pass_api
def inspect(config, id, raw):
    """
    Get details of didimos

    <ID> is the didimo ID to get information.

    Multiple didimo IDs are accepted, separated by a space or newline

    If <ID> is the character "-", read the IDs from STDIN.

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

    if raw:
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

@cli.command()
@click.help_option(*HELP_OPTION_NAMES)
@click.argument("id", required=True)
@pass_api
def delete(config, id):
    """
    Delete a didimo

    <id> is the didimo key

    """
    #

    api_path = "/v3/didimos/"
    url = config.api_host + api_path + id

    r = http_delete(url, auth=DidimoAuth(config, api_path))

    if r.status_code != 204:
        if r.status_code == 404:
            click.secho('No didimo with the requested key was found on this account', err=True, fg='red')
        else:
            click.secho('Error %d' % r.status_code, err=True, fg='red')
        sys.exit(1)

    click.secho('Deleted!', err=False, fg='blue')


@cli.command()
@click.help_option(*HELP_OPTION_NAMES)
@click.argument("id", required=True)
@click.argument("name", required=True)
@click.argument("value", required=True)
@pass_api
def set_metadata(config, id, name, value):
    """
    Sets metadata on a didimo

    <id> is the didimo key
    <name> is the metadata key
    <value> is the metadata value

    """
    api_path = "/v3/didimos/"+id+"/meta_data"
    url = config.api_host + api_path

    payload = {'name': name, 'value': value}
    
    r = http_post_no_break(url, auth=DidimoAuth(config, api_path), json=payload) 

    if r.status_code != 201:
        if r.status_code == 404:
            click.secho('No didimo with the requested key was found on this account', err=True, fg='red')
        elif r.status_code == 400:
            click.secho('Please correct your input.', err=True, fg='red')
        else:
            click.secho('Error %d' % r.status_code, err=True, fg='red')
        sys.exit(1)
    click.secho('Metadata - Name: '+name+' Value: '+str(value), err=False, fg='blue')

@cli.command()
@click.help_option(*HELP_OPTION_NAMES)
@click.argument("id", required=True)
@click.argument("name", required=True)
@pass_api
def get_metadata(config, id, name):
    """
    Retrieves metadata on a didimo

    <id> is the didimo key
    <name> is the metadata key

    """
    api_path = "/v3/didimos/"+id+"/meta_data/"+name
    url = config.api_host + api_path

    
    r = http_get(url, auth=DidimoAuth(config, api_path)) 

    if r.status_code != 200:
        if r.status_code == 404:
            click.secho('No didimo with the requested key was found on this account', err=True, fg='red')
        elif r.status_code == 400:
            click.secho('Please correct your input.', err=True, fg='red')
        else:
            click.secho('Error %d' % r.status_code, err=True, fg='red')
        sys.exit(1)

    response = r.json()
    click.secho('Metadata - Name: '+name+' Value: '+str(response['value']), err=False, fg='blue')

@cli.command()
@click.help_option(*HELP_OPTION_NAMES)
@click.argument("id", required=True)
@click.argument("name", required=True)
@click.argument("value", required=True)
@pass_api
def update_metadata(config, id, name, value):
    """
    Updates metadata on a didimo

    <id> is the didimo key
    <name> is the metadata key
    <value> is the new metadata value

    """
    api_path = "/v3/didimos/"+id+"/meta_data/"+name
    url = config.api_host + api_path

    payload = {'name': name, 'value': value}
    
    r = http_put(url, auth=DidimoAuth(config, api_path), json=payload) 

    if r.status_code != 200:
        if r.status_code == 404:
            click.secho('No didimo with the requested key was found on this account', err=True, fg='red')
        elif r.status_code == 403:
            click.secho('The didimo\'s metadata item cannot be updated because it is not user-defined.', err=True, fg='red')
        elif r.status_code == 400:
            click.secho('Please correct your input.', err=True, fg='red')
        else:
            click.secho('Error %d' % r.status_code, err=True, fg='red')
        sys.exit(1)
    click.secho('Updated!', err=False, fg='blue')

@cli.command()
@click.help_option(*HELP_OPTION_NAMES)
@click.argument("id", required=True)
@click.argument("name", required=True)
@pass_api
def delete_metadata(config, id, name):
    """
    Deletes metadata on a didimo

    <id> is the didimo key
    <name> is the metadata key

    """
    api_path = "/v3/didimos/"+id+"/meta_data/"+name
    url = config.api_host + api_path
    
    r = http_delete(url, auth=DidimoAuth(config, api_path)) 

    if r.status_code != 204:
        if r.status_code == 404:
            click.secho('No didimo with the requested key was found on this account', err=True, fg='red')
        elif r.status_code == 403:
            click.secho('The didimo\'s metadata item cannot be deleted because it is not user-defined.', err=True, fg='red')
        elif r.status_code == 400:
            click.secho('Please correct your input.', err=True, fg='red')
        else:
            click.secho('Error %d' % r.status_code, err=True, fg='red')
        sys.exit(1)
    click.secho('Deleted!', err=False, fg='blue')


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

