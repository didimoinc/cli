import click
from datetime import datetime


def print_key_value(key, value, fg="white"):
    click.secho("%s: " % key, bold=True, nl=False, fg=fg, err=True)
    click.secho(str(value), err=True)


def print_status_header():
    click.secho("{:<18} │ {:<10} │ {:<7} │ {:^4} │ {:^4}  "
                .format(
                    'didimo ID', 'Type', 'Percent', 'Status', 'Created At'),
                bold=True, err=True)
    click.secho("─" * 112)


def print_status_row(didimo):

    # Remove when /status endpoint is consistent with /list
    if didimo.get('status') == "error":
        click.secho("{:<18} │ {:<10} │ {:<7} │ {:<6} │ {:^4}  "
                    .format(didimo['key'], "-", "-",
                             didimo['status'].title(), "-"), fg="red")
        return

    color = 'white'
    if didimo['status'] == "error":
        color = 'red'
    elif didimo['status'] == "done":
        color = 'green'
    elif didimo['status'] == "processing":
        color = 'yellow'

    didimo_type = didimo['input_type']
    if didimo['input_type'] == "lofimesh_texture":
        didimo_type = 'sony'
    elif didimo['input_type'] == "hifimesh_texture_photo":
        didimo_type = 'scan'
    elif didimo['input_type'] == "blendshapes":
        didimo_type = 'blend'
    elif didimo['input_type'] == "vertexdeform":
        didimo_type = 'vertx'

    #created_at = datetime.strptime(didimo['created_at'], "%Y-%m-%d %H:%M:%S")
    click.secho("{:<18} │ {:<10} │ {:<7} │ {:^7}│ {:^7}"
                .format(
                    didimo['key'], didimo_type.title(),
                    didimo['percent'],
                    didimo['status'].title(),
                    didimo['created_at']),
                fg=color)

def create_set(ids):
    return set(ids)

#Didimo Generation Templates
def print_didimo_generation_template_header():
    click.secho("{:<36} │ {:<10} │ {:<6} │ {:<25} │ {:<42} │ {:^7}  "
                .format(
                    'DGT UUID', 'Created At', 'Scope', 'Name', 'Description', 'Settings'),
                bold=True, err=False)
    click.secho("─" * 232)


def print_didimo_generation_template_row(dgt):

    if 'profile_id' in dgt and 'account_id' in dgt:
        scope = "user"
    else:
        scope = "system"

    if scope == "system":
        color = 'yellow'
    else:
        color = 'white'

    truncated_name = dgt['template_name'][0:20]
    if len(dgt['template_name']) != len (truncated_name):
        truncated_name = truncated_name + "(...)"

    if 'description' in dgt and dgt['description'] != None:
        truncated_description = dgt['description'][0:37]
        if len(dgt['description']) != len (truncated_description):
            truncated_description = truncated_description + "(...)"
    else:
        truncated_description = ""

    created_at_datetime = datetime.strptime(dgt['created_at'], "%Y-%m-%dT%H:%M:%S")
    created_at = created_at_datetime.strftime("%Y-%m-%d")

    

    click.secho("{:<36} │ {:<10} │ {:<6} │ {:<25} │ {:<43}│ {:^7}"
                .format(
                    dgt['uuid'],
                    created_at,
                    scope,
                    truncated_name,
                    truncated_description,
                    str(dgt['settings'])),
                fg=color)


#Bulk requests
def print_bulk_requests_header():
    click.secho("{:<36} │ {:<10} │ {:<10} │ {:<7}"
                .format(
                    'Bulk UUID', 'Created At', 'Status', '#Items'),
                bold=True, err=False)
    click.secho("─" * 72)


def print_bulk_requests_row(bulk_request):

    if 'status' in bulk_request and bulk_request['status']=='completed':
        color = 'green'
    elif 'status' in bulk_request and bulk_request['status']=='error':
        color = 'red'
    else:
        color = 'white'

    created_at_datetime = datetime.strptime(bulk_request['created_at'], "%Y-%m-%dT%H:%M:%S")
    created_at = created_at_datetime.strftime("%Y-%m-%d")

    items_count = len(bulk_request['items'])

    click.secho("{:<36} │ {:<10} │ {:<10} │ {:<7}"
                .format(
                    bulk_request['uuid'],
                    created_at,
                    bulk_request['status'],
                    str(items_count)),
                fg=color)

def print_bulk_request_item_header():
    click.secho("{:<36} │ {:<10} │ {:<18} │ {:<7}"
                .format(
                    'Item UUID', 'Status', 'Key', 'File'),
                bold=True, err=False)
    click.secho("─" * 92)

def print_bulk_request_item_row(bulk_request_item):

    if 'status' in bulk_request_item and bulk_request_item['status']=='completed':
        color = 'green'
    elif 'status' in bulk_request_item and bulk_request_item['status']=='error':
        color = 'red'
    else:
        color = 'white'

    click.secho("{:<36} │ {:<10} │ {:<18} │ {:<7}"
                .format(
                    bulk_request_item['uuid'],
                    bulk_request_item['status'],
                    bulk_request_item['request_key'],
                    bulk_request_item['file']),
                fg=color)


