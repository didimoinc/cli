import click
from datetime import datetime


def print_key_value(key, value, fg="white"):
    click.secho("%s: " % key, bold=True, nl=False, fg=fg, err=True)
    click.secho(str(value), err=True)


def print_status_header():
    click.secho("{:<18} │ {:<5} │ {:<7} │ {:^4} │ {:^4}  "
                .format(
                    'didimo ID', 'Type', 'Percent', 'Status', 'Created At'),
                bold=True, err=True)
    click.secho("─" * 112)


def print_status_row(didimo):

    # Remove when /status endpoint is consistent with /list
    if didimo.get('status') == "error":
        click.secho("{:<18} │ {:<5} │ {:<7} │ {:<6} │ {:^4}  "
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
    click.secho("{:<18} │ {:<5} │ {:<7} │ {:^7}│ {:^7}"
                .format(
                    didimo['key'], didimo_type.title(),
                    didimo['percent'],
                    didimo['status'].title(),
                    didimo['created_at']),
                fg=color)
