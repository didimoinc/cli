import click
import json
import sys
import time
import platform
import zipfile
import os
import fnmatch
import re
import shutil
import multiprocessing
from multiprocessing import current_process 
from multiprocessing import Process

from .shared_queue import MyQueue, SharedCounter
from .helpers import DidimoNotFoundException, wait_for_dgp_completion, download_asset, download_didimo, get_didimo_status, get_asset_status, get_output_display_type_json_flag
from .network import DidimoAuth, http_post_withphoto, http_get_no_error, http_get, http_delete#, http_post, http_post_no_break, http_put, cache_this_call, clear_network_cache
from .utils import print_didimo_generation_template_header, print_didimo_generation_template_row, print_bulk_requests_header, print_bulk_requests_row, print_bulk_request_item_header, print_bulk_request_item_row

def new_aux_shared_preprocess_batch_files(input, input_type, output_display_type_json_flag):
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
            click.echo("Zip processing is only available for the photo input type. Please correct the command and try again.")
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
                if output_display_type_json_flag:
                    return {
                                "error": 1,
                                "input":input,
                                "message":"file not supported"
                           }
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
                    if not output_display_type_json_flag:
                        print(path_prefix + input_file)

            if not output_display_type_json_flag:
                batch_total_files = len(fnmatch.filter(batch_files, '*.*'))
                click.echo("Batch processing - files count: " + str(batch_total_files))

            return batch_files
    else:
        return None

def new_aux_shared_upload_core(config, url, input_file, depth, input_archive, payload, output_display_type_json_flag):
    """
    Shared code that handles a single upload request
    """
    r = http_post_withphoto(url, config.access_key, payload, input_file, depth, input_archive, False)

    if input_archive != None:
        input_file = input_archive

    if r.status_code != 200 and r.status_code != 201:
        if not output_display_type_json_flag:
            click.secho('\nError %d uploading %s: %s' % (r.status_code, input_file, r.text), err=True, fg='red')
        return {
                "error": 1,
                "input_file":input_file,
                "status_code":r.status_code,
                "message":r.json()['description']
               }
    elif input_archive != None:
        return {
                "error": 0,
                "input_file":input_archive,
                "status_code":r.status_code,
                "full_response":str(r.json())
               }
    else:
        didimo_id = r.json()['key']
        return {
                "error": 0,
                "input_file":input_file,
                "status_code":r.status_code,
                "didimo_id":didimo_id
               }


def new_aux_shared_processing(config, didimo_id, output_display_type_json_flag):
    """
    Shared code that handles the didimo processing polling stage 
    """
    no_error = None
    percent = None
    status_msg = None

    if not output_display_type_json_flag:
        with click.progressbar(length=100, label='Creating didimo '+didimo_id, show_eta=False) as bar:
            last_value = 0
            initing_progress_bar = True
            while True:
                if initing_progress_bar:
                    bar.update(0)
                    initing_progress_bar = False
                else:
                    response = get_didimo_status(config, didimo_id)
                    status = response['status']
                    status_msg = response['status_message']
                    percent = response.get('percent', 100)
                    update = percent - last_value
                    last_value = percent
                    bar.update(update)
                    if status == 'done':
                        no_error = True
                        break
                    elif status_msg != "":
                        no_error = False
                        click.secho(err=True)
                        click.secho('Error generating didimo %s from %s: %s' % (didimo_id, str(input_file), response["status_message"]), err=True, fg='red')
                        break   
                time.sleep(2)
    else:
        while True:
            response = get_didimo_status(config, didimo_id)
            status = response['status']
            status_msg = response['status_message']
            percent = response.get('percent', 100)
            if status == 'done':
                no_error = True
                break
            elif status_msg != "":
                no_error = False
                break
            time.sleep(2)

    if no_error == True:
        return {
                "error": 0,
                "didimo_key":didimo_id,
                "percent": percent,
                "message":response['status_message']
               }
    else:
        #print(str(response))
        return {
                "error": 1,
                "didimo_key":didimo_id,
                "percent": percent,
                "message":response['status_message']
               }


def new_aux_shared_upload(config, url, batch_files, depth, payload, output_display_type_json_flag):
    """
    Shared code that handles the whole upload process
    """
    all_upload_error_responses = []
    batch_didimo_ids = []

    if output_display_type_json_flag:
        for input_file in batch_files:

            r = new_aux_shared_upload_core(config, url, input_file, depth, None, payload, output_display_type_json_flag)
            r_json = r#.json()
            if r_json['error'] == 1:
                all_upload_error_responses.append(r)
                didimo_id = None
            else:
                didimo_id = r_json['didimo_id']
            batch_didimo_ids.append(didimo_id)

    else:
        with click.progressbar(length=len(batch_files), label='Uploading files...', show_eta=False) as bar:
            last_value = 0
            i = 0
            
            for input_file in batch_files:

                r = new_aux_shared_upload_core(config, url, input_file, depth, None, payload, output_display_type_json_flag)
                r_json = r#.json()
                if r_json['error'] == 1:
                    all_upload_error_responses.append(r)
                    didimo_id = None
                    click.secho('\nError %d uploading %s: %s' % (r.status_code, input_file, r.text), err=True, fg='red')
                else:
                    didimo_id = r_json['didimo_id']
                batch_didimo_ids.append(didimo_id)

                i = i + 1
                update = i - last_value
                last_value = i
                bar.update(update)

                #click.echo(""+str(i)+"/"+str(len(batch_files)))

    return {
            "upload_error_responses":all_upload_error_responses,
            "batch_didimo_ids":batch_didimo_ids
           }


def new_aux_shared_upload_processing_and_download(config, url, batch_files, depth, payload, no_wait, no_download, output, batch_flag, output_display_type_json_flag):
    """
    Shared code that handles polling status and managing download
    """
    all_upload_error_responses = []
    all_processing_error_responses = []
    all_download_responses = []
    
    batch_didimo_ids = []
    #click.echo("Uploading files...")

    r = new_aux_shared_upload(config, url, batch_files, depth, payload, output_display_type_json_flag)
    all_upload_error_responses = r['upload_error_responses']
    batch_didimo_ids = r['batch_didimo_ids']

    if len(all_upload_error_responses) == len(batch_didimo_ids): #break early if all uploads failed
        click.echo(json.dumps({
                        "upload_errors":all_upload_error_responses
                       }))
        return

    if not output_display_type_json_flag:
        click.echo("Checking progress...")

    complete_tasks = MyQueue()
    jobs = []
    i = 0
    valid_processing_count = 0
    valid_download_count = 0
    for input_file in batch_files:

        if not no_wait:

            didimo_id = batch_didimo_ids[i]
            i = i + 1

            if didimo_id == None:
                continue

            if batch_flag: #fork and don't output progress bars

                no_error = None

                r = new_aux_shared_processing(config, didimo_id, output_display_type_json_flag)
                if r["error"] == 1:
                    all_processing_error_responses.append(r)
                else:
                    valid_processing_count = valid_processing_count + 1
       
                    if not no_download:
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
                r = new_aux_shared_processing(config, didimo_id, output_display_type_json_flag)
                if r["error"] == 1:
                    all_processing_error_responses.append(r)
                elif not no_download:
                    if output is None:
                        output = ""
                    else:
                        if not output.endswith('/'):
                            output = output + "/"
                    download_response = download_didimo(config, didimo_id, "", output)
                    all_download_responses = all_download_responses + [download_response]
                    #if download_response["error"] == 0:
                    #    valid_download_count = valid_download_count + 1

    if no_download:
        if output_display_type_json_flag:
            click.echo(json.dumps( 
                            {
                                "upload_errors":all_upload_error_responses,
                                "processing_errors":all_processing_error_responses
                            }))
    else:
        #check if child processes are still running and wait for them to finish
        if batch_flag and valid_processing_count > 0:
            if not output_display_type_json_flag:
                click.echo("Please wait while the remaining files are finished downloading...")
            for job in jobs:
                job.join()

        if batch_flag:
            all_download_responses = complete_tasks.as_array()

        if output_display_type_json_flag:
            click.echo(json.dumps( {
                                "upload_errors":all_upload_error_responses,
                                "processing_errors":all_processing_error_responses,
                                "download_results":all_download_responses
                            }))
            return

        for download_response in all_download_responses:
            if download_response["download_error"] == False:
                valid_download_count = valid_download_count + 1

        if valid_download_count > 0:
            failed_download_count = len(all_download_responses) - valid_download_count
            click.echo("Process finished - Successful downloads: %d | Download errors: %d" % (valid_download_count, failed_download_count) )
        else:
            click.echo("All downloads failed!")


def download_didimo_subprocess(config, didimo_id, package_type, output, showProgressBar, complete_tasks):
    download_response = download_didimo(config, didimo_id, package_type, output, showProgressBar)
    complete_tasks.put(download_response) #complete_tasks.put(didimo_id + ' is done by ' + current_process().name)


def deformation_aux_shared_processing_and_download(config, timeout, request, api_path, outputFileSuffix, output_display_type_json_flag):
    """
    Shared code that handles polling status and managing download of deformed assets
    """

    request_response = request.text

    if request.status_code != 201:
        if not output_display_type_json_flag:
            click.secho('Error %d' % request.status_code, err=True, fg='red')
            click.echo(request.text)
        else:
            cmd_response_json = {
                              "input_error": True,
                              "request_response": request.json()
                            }
            click.echo(str(cmd_response_json))
        sys.exit(1)

    response = request.json()

    key = response['key']
    url = ""
    for package_itm in request.json()['transfer_formats']:
        url = package_itm["__links"]["self"]
        break

    curr_dir = os.getcwd()
    if not curr_dir.endswith('/'):
        curr_dir = curr_dir + "/"
    output = "%s.zip" % (curr_dir + key + outputFileSuffix)

    if not output_display_type_json_flag:
        click.echo("Creating package file.")
    error_status = wait_for_dgp_completion(config, key, timeout, output_display_type_json_flag)
    if error_status:
        if not output_display_type_json_flag:
            click.echo("There was an error creating package file. Download aborted.")
        else:
            cmd_response_json = {
                              "input_error": True,
                              "request_response": response, 
                              "processing_error": error_status
                            }
            click.echo(str(cmd_response_json))
            sys.exit(1)
    else:
        download_response = download_asset(config, url, api_path, output, output_display_type_json_flag)

    if output_display_type_json_flag:
        cmd_response_json = {
                              "input_error": False,
                              "request_response": response, 
                              "processing_error": error_status,
                              "download_response": download_response
                            }
        click.echo(str(cmd_response_json))


def get_didimo_generation_template_aux(config, uuid, output_display_type, return_object_flag = False):
    """
    (Shared Implementation) Retrieves a didimo generation template

    <uuid> is the didimo generation template UUID
    """
    output_display_type_json_flag = get_output_display_type_json_flag(config, output_display_type)

    api_path = "/v3/didimo_generation_templates/"+uuid
    url = config.api_host + api_path

    r = http_get_no_error(url, auth=DidimoAuth(config, api_path)) 

    if return_object_flag:
        return r
    elif output_display_type_json_flag:
        click.echo(r.text)
    else:
        if r.status_code != 200:
            if r.status_code == 404:
                res = r.json()
                click.secho('No didimo generation template with the requested uuid was found.', err=True, fg='red')
            elif r.status_code == 400:
                click.secho('Please correct your input.', err=True, fg='red')
            else:
                click.secho('Error %d' % r.status_code, err=True, fg='red')
            sys.exit(1)

        response = r.json()

        print_didimo_generation_template_header()
        print_didimo_generation_template_row(response)

def delete_didimo_generation_template_aux(config, uuid, output_display_type):
    """
    (Shared Implementation) Deletes a didimo generation template

    <uuid> is the didimo generation template UUID
    """
    output_display_type_json_flag = get_output_display_type_json_flag(config, output_display_type)

    api_path = "/v3/didimo_generation_templates/"+uuid
    url = config.api_host + api_path
    
    r = http_delete(url, auth=DidimoAuth(config, api_path)) 

    if output_display_type_json_flag:
        click.echo(r.text)
    else:
        if r.status_code != 204:
            if r.status_code == 404:
                #res = r.json()
                click.secho('No didimo generation template with the requested uuid was found.', err=True, fg='red')
            elif r.status_code == 403:
                click.secho('Insufficient priviledges: the didimo generation template cannot be deleted because it is not user-defined.', err=True, fg='red')
            elif r.status_code == 400:
                click.secho('Please correct your input.', err=True, fg='red')
            else:
                click.secho('Error %d' % r.status_code, err=True, fg='red')
            sys.exit(1)
        click.secho('Deleted!', err=False, fg='blue')


def generation_template_shared_response_processing(response, output_display_type_json_flag):
    if output_display_type_json_flag:
        click.echo(response.text)
    else:
        if response.status_code != 200 and response.status_code != 201:
            if response.status_code == 404:
                click.secho('Not found.', err=True, fg='red')
            elif response.status_code == 400:
                click.secho('Please correct your input.', err=True, fg='red')
            else:
                click.secho('Error %d' % response.status_code, err=True, fg='red')
            click.echo(response.text)
            sys.exit(1)

        json_response = response.json()
        print_didimo_generation_template_header()
        print_didimo_generation_template_row(json_response)

def bulk_list_aux(config, group_type, status_filter, output_display_type):
    """
    (Shared Implementation) Lists bulk requests
    """
    output_display_type_json_flag = get_output_display_type_json_flag(config, output_display_type)
    
    api_path = "/v3/"+group_type+"/bulks"
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

            _bulks = json_response['bulk_requests']
            next_page = json_response['__links']['next'] if '__links' in json_response and 'next' in json_response['__links'] else None

            print_bulk_requests_header()
            for _bulk in _bulks:
                if not status_filter or _bulk["status"] == status_filter:
                    print_bulk_requests_row(_bulk)

            if next_page != None:
                click.confirm('There are more results. Fetch next page?', abort=True)

                api_path = next_page
                url = api_path
                r = http_get(url, auth=DidimoAuth(config, api_path))
            else:
                break

def bulk_get_aux(config, group_type, uuid, output_display_type):
    """
    (Shared Implementation) Get bulk request details
    """
    output_display_type_json_flag = get_output_display_type_json_flag(config, output_display_type)
    
    api_path = "/v3/"+group_type+"/bulks/"+uuid
    url = config.api_host + api_path

    r = http_get_no_error(url, auth=DidimoAuth(config, api_path)) 

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

        json_response = r.json()

        print_bulk_requests_header()
        print_bulk_requests_row(json_response)

        print_bulk_request_item_header()
        for _item in json_response['items']:
            print_bulk_request_item_row(_item)
