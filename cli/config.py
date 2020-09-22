import click
import json
import sys
import os

from pathlib import Path

class Config(object):
    def __init__(self):
        self.access_key = ""
        self.secret_key = ""
        self.configuration = ""
        self.api_host = ""

    def init(self, configuration, host, api_key, api_secret):
        config_dir = Path.home() / ".didimo"
        config_dir.mkdir(parents=True, exist_ok=True)

        config_file = config_dir / ("%s.json" % configuration)
        if config_file.exists():
            overwrite = click.confirm('Found a configuration for %s. Overwrite?' % configuration)
            if not overwrite:
                click.echo('Discarding changes', err=True)
                sys.exit(0)

        with click.open_file(config_file, "w") as f:
            config = {"host": host, "access_key": api_key, "secret_key": api_secret}
            json.dump(config, f, indent=2)
            click.secho("Wrote configuration at %s" % config_file, err=True)

        cli_config_file = config_dir / "cli.json"
        with click.open_file(cli_config_file, "w") as f:
            config = {"default": configuration}
            json.dump(config, f, indent=2, sort_keys=True)
            click.secho("Set \"%s\" as default configuration" % configuration, err=True)

    def load(self):
        try:
            with click.open_file(Path.home() / ".didimo" / "cli.json", "r") as f:
                config = json.load(f)
                self.configuration = config["default"]
        except FileNotFoundError:
            click.secho("CLI configuration file not found. Run `didimo init`", err=True, fg='red')
            sys.exit(1)
        except json.decoder.JSONDecodeError:
            click.secho("Error decoding JSON from \"cli.json\"", err=True, fg='red')
            sys.exit(1)

    def list_configurations(self):
        config_dir = Path.home() / ".didimo"
        envs = sorted([f for f in os.listdir(config_dir) if f.endswith(".json")])
        for e in envs:
            env = e.split('/')[-1].split('.')[0]
            if env != "cli":
                if env == self.configuration:
                    click.secho(env, bold=True, err=True, nl=False)
                    click.secho(" [x]", bold=True, fg='blue')
                else:
                    click.secho(env, err=True)

    def load_configuration(self, configuration):
        config_file = Path.home() / ".didimo" / (configuration + ".json")
        if not config_file.exists():
            click.secho("No configuration file for \"%s\"." % configuration, err=True, fg='red')
            sys.exit(1)

        try:
            with click.open_file(config_file, 'r') as f:
                config = json.load(f)
                self.api_host = config.get("host", "")
                self.access_key = config.get("access_key", "")
                self.secret_key = config.get("secret_key", "")
                if self.access_key == "" or self.secret_key == "":
                    click.secho("No access key or secret key for \"%s\" configuration" % configuration, err=True, fg='red')
                    sys.exit(1)
                if self.api_host == "":
                    click.secho("No API host for \"%s\" configuration" % configuration, err=True, fg='red')
                    sys.exit(1)
        except json.decoder.JSONDecodeError:
            click.secho("Error decoding configuration file %s" % config_file, err=True, fg='red')
            sys.exit(1)

    def save_configuration(self, configuration):
        config_file = Path.home() / ".didimo" / (configuration + ".json")
        if not config_file.exists():
            click.secho("No configuration file for \"%s\"." % configuration, err=True, fg='red')
            sys.exit(1)

        cli_file = Path.home() / ".didimo" / "cli.json"
        with click.open_file(cli_file, "w") as f:
            config = {"default": configuration}
            json.dump(config, f, indent=2, sort_keys=True)
