from urllib import parse as urlparse
import click
import sys
import time
import multiprocessing

from .network import DidimoAuth, http_get, cache_this_call
from .utils import print_status_header, print_status_row
from ._version import __version__


class DidimoNotFoundException(Exception):
    pass


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
    if r.status_code == 404:
        raise DidimoNotFoundException()
    return r.json()

def get_asset_status(config, id):
    api_path = "/v3/assets/" + id
    url = config.api_host + api_path
    r = http_get(url, auth=DidimoAuth(config, api_path))
    return r.json()

#Polls the API for progress update until the didimo generation pipeline is finished. Returns 0 if the process is successfull or return 1 if there is an error. 
def wait_for_dgp_completion(config, key, timeout, output_display_type_json_flag):

    manager = multiprocessing.Manager()
    return_dict = manager.dict()

    if timeout is not None:
        # Start foo as a process
        p = multiprocessing.Process(target=wait_for_dgp_completion_aux, name="Wait_for_dgp_completion_aux", args=(config,key,output_display_type_json_flag, return_dict))
        p.start()

        # Wait 10 seconds for foo
        p.join(float(timeout))

        # If thread is active
        if p.is_alive():
            if not output_display_type_json_flag:
                click.secho("Timeout!")

            # Terminate foo
            p.terminate()

            # Cleanup
            p.join()

            return 3 #return timeout error
        else:
            return return_dict[0] #return function result
    else:
        wait_for_dgp_completion_aux(config, key, output_display_type_json_flag, return_dict)
        return return_dict[0]


def wait_for_dgp_completion_aux(config, key, output_display_type_json_flag, return_dict):

    last_status = ""
    while True:
        response = get_asset_status(config, key) 
        percent = response.get('percent', 100)
        status = response.get('status', '')

        if status != last_status:
            last_status = status
            if not output_display_type_json_flag:
                click.secho("Status: "+str(status))

        if status == "processing":
            if not output_display_type_json_flag:
                click.secho("Progress: "+str(percent))

        if response['status_message'] != "":
            if not output_display_type_json_flag:
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
    
    if r.status_code == 404:
        click.secho('No didimo with the requested key was found on this account.', err=True, fg='red')
        sys.exit(0)

    return_json_item = None

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
                    click.secho('Downloaded to %s' % output_filename, fg='blue', err=False)
                return_json_item = {
                                    "download_error":False,
                                    "url":s3url,
                                    "output_filename":output_filename,
                                    "error_message":None
                                   }
            except Exception as error: 
                return_json_item = {
                                    "download_error":True,
                                    "url":s3url,
                                    "output_filename":output_filename,
                                    "error_message":error
                                   }
                if showProgressBar:
                    click.secho('Error downloading to %s: %s' % (output_filename, error), fg='red', err=True)

        return return_json_item


def download_asset(config, asset_url, api_path, output_path, output_display_type_json_flag):

    if asset_url != "":
        with http_get(asset_url, auth=DidimoAuth(config, api_path)) as r:
            r.raise_for_status()
            zipsize = int(r.headers.get('content-length', 0))
            with click.open_file(output_path, 'wb') as f:
                if output_display_type_json_flag:
                    for chunk in r.iter_content(chunk_size=2048):
                        size = f.write(chunk)
                else:
                    label = "Downloading asset"
                    click.echo(label)
                    with click.progressbar(length=zipsize, label=label) as bar:
                        for chunk in r.iter_content(chunk_size=2048):
                            size = f.write(chunk)
                            bar.update(size)
                    click.secho('Downloaded to %s' % output_path, fg='blue', err=False)
                return {
                          "error": 0,
                          "output_path": output_path,
                          "size": zipsize
                        }    
    else:
        if output_display_type_json_flag:
            return {
                      "error": 1,
                      "message": "Unable to download"
                    }
        else:
            click.secho("Unable to download", fg='red', err=True)


def get_cli_version_compatibility_rules(config, output_display_type = "ignore_display_rules"):

    output_display_type_json_flag = get_output_display_type_json_flag(config, output_display_type)

    #Get the current CLI version compatibility rules 

    api_path = "/v3/platforms/cli"
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

        for version in response["versions"]:
            if version["code"] == __version__:
                return version["dgp_compatibility_rules"]

        return "CLI version not found"

        return compatibility_json


def get_output_display_type_json_flag(config, output_display_type):
    """
    Calculates the value of the output_display_type_json_flag based on the active configuration and the param value that overrides it. Default is human readable for backward compatibility.
    """
    if  output_display_type != "ignore_display_rules" and ((output_display_type != None and output_display_type == "json") or (output_display_type == None and config.output_display_type == "json")):
        output_display_type_json_flag = True
    else:
        output_display_type_json_flag = False
    return output_display_type_json_flag

def list_aux(config, api_path, page_size, index, navigate, sort_by, sort_order, output_display_type):
    """
    List didimos
    """
    output_display_type_json_flag = get_output_display_type_json_flag(config, output_display_type)

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
            if output_display_type_json_flag:
                click.echo(str({"error": 1,"message":"Unknown sort order! Please correct the input. "}))
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
        if output_display_type_json_flag:
            click.echo(str({"error": 1,"message":"An error has occurred! Aborting..."}))
        else: 
            click.echo("An error has occurred! Aborting...")
        exit(1);

    if output_display_type_json_flag:
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
