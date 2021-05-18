## Didimo CLI

 - Website: https://www.didimo.co
 - Customer Portal: https://app.didimo.co
 - Documentation: https://docs.didimo.co

Didimo CLI is a command-line interface to our API.

```
$ didimo --help
Usage: didimo [OPTIONS] COMMAND [ARGS]...

  Create, list and download didimos

Options:
  -c, --config TEXT  Use this configuration instead of the default one.
  -h, --help         Show this message and exit.

Commands:
  account   Get account information
  config    Get or set configuration
  download  Download a didimo
  execute   Execute on-demand features on didimos
  init      Initializes configuration
  list      List didimos
  new       Create a didimo
  status    Get status of didimos
  version   Print version and exit
```

These are the features that are implemented at the moment:

 - **Create** didimos, supporting different input types, package types, versions and features
 - **List** didimos
 - **Download** didimos, supporting different package types
 - **Execute** on-demand features on didimos
 - **Supports multiple profiles** as an easy way to change between environments or even accounts


### Quickstart

##### 1. Install

The CLI is written in Python 3 and is distributed as package on PyPI
and can be installed with pip.

```bash
pip3 install didimo-cli
```

##### 2. Configure with your API Key

Create a new configuration and input your API Key. If you do not have an API Key,
please refer to the [Getting an API Key](#getting-an-api-key) section.

```bash
didimo init <configuration name>
```

After setting up the CLI, you can check your account with:

```bash
didimo account
```

##### 3. Create a didimo

Now that the CLI is configured, let's create a didimo based on a photo.

```bash
didimo new photo <path to the photo>
```

The CLI waits for the didimo to be created and downloads the result in a zip
file.

You can list your didimos with:

```bash
didimo list
```

For more help, check the documentation on each command with the `--help` option.

### Getting an API Key

Go to the [Customer Portal](https://app.didimo.co) and register for an account.

Make sure that you tick the "Developer Account" checkbox in order to unlock
the "Developers" section on the sidebar.

After that, go to "Developers" > "Applications" and create an Application and
an API Key. Copy the information and paste on a text editor in order to
see every detail of your credentials
