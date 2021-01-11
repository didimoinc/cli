import click
from datetime import datetime

def print_key_value(key, value, fg="white"):
    click.secho("%s: " % key, bold=True, nl=False, fg=fg, err=True)
    click.secho(str(value), err=True)

def print_status_header():
    click.secho("{:<18} │ {:<5} │ {:<7} │ {:^4} │ {:^4} │ {:^4} │ {:<7} │ {:<10} │ {:<19} │ {:<8}"
                .format(
                    'didimo ID','Type','Version','Bsic',
                    'Expr','Vsms','Percent','Status','Created At', 'Elapsed'),
                bold=True, err=True)
    click.secho("─" * 112)

def print_status_row(didimo):
    # Remove when /status endpoint is consistent with /list
    if didimo.get('stt') == "NOK":
        click.secho("{:<18} │ {:<5} │ {:<7} │ {:^4} │ {:^4} │ {:^4} │ {:<7} │ {:<10} │ {:<19} │ {:<8}"
            .format(didimo['key'], "-", "-", "-", "-",
                    "-", "-", didimo['status'].title(), "-", "-"), fg="red")
        return

    color = 'white'
    if didimo['status'] == "error":
        color = 'red'
    elif didimo['status'] == "done":
        color = 'green'
    elif didimo['status'] == "processing":
        color = 'yellow'

    didimo_type = didimo['type']
    if didimo['type'] == "lofimesh_texture":
        didimo_type = 'sony'
    elif didimo['type'] == "hifimesh_texture_photo":
        didimo_type = 'scan'
    elif didimo['type'] == "blendshapes":
        didimo_type = 'blend'
    elif didimo['type'] == "vertexdeform":
        didimo_type = 'vertx'

    basic = expressions = visemes = '○'
    if 'basic' in didimo['optional_features'].split(','):
        basic = '●'
    if 'expressions' in didimo['optional_features'].split(','):
        expressions = '●'
    if 'visemes' in didimo['optional_features'].split(','):
        visemes = '●'

    created_at = datetime.strptime(didimo['created_at'], "%Y-%m-%d %H:%M:%S")
    updated_at = datetime.strptime(didimo['updated_at'], "%Y-%m-%d %H:%M:%S")
    click.secho("{:<18} │ {:<5} │ {:<7} │ {:^4} │ {:^4} │ {:^4} │ {:<7} │ {:<10} │ {:<19} │ {:<8}"
            .format(
                didimo['key'], didimo_type.title(),
                didimo['template_version'], basic, expressions,
                visemes, didimo['percent'],
                didimo['status'].title(),
                didimo['created_at'], str(updated_at - created_at)),
            fg=color)
