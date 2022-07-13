## Didimo CLI

 - Website: https://www.didimo.co
 - Customer Portal: https://app.didimo.co
 - Documentation: https://developer.didimo.co

Didimo CLI is a command-line interface to our API.

```
$ didimo --help
Usage: didimo [OPTIONS] COMMAND [ARGS]...

  Create, list and download didimos

Options:
  -c, --config TEXT  Use this configuration instead of the default one.
  -h, --help         Show this message and exit.

Commands:
  account                           Get account information
  clear-cache                       Clears cache and exit
  config                            Get or set configuration
  download                          Download a didimo
  execute                           Execute on-demand features on didimos
  init                              Initializes configuration
  list                              List didimos
  list-demo-didimos                 List demo didimos
  vertexdeform                      Deform a model
  new                               Create a didimo
  status                            Get status of didimos
  version                           Print version and exit
  version-api                       Print api dgp version and exit
  version-cli-compatibility-rules   Print cli compatibility rules and exit
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

If you already have a previous version installed, you should execute:

```bash
pip3 install didimo-cli --upgrade
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

Generating a didimo may include several options, as described on our developer portal.

Didimo CLI currently accepts the following features (-f):
- oculus_lipsync
- simple_poses
- arkit
- aws_polly

The CLI accepts following output formats (-p):
- glTF
- FBX

In addition to those, it also accepts the definition of other parameters:
- the maximum texture dimension (-m)
- the avatar structure, which controls the output as a full-body or a head-only didimo (--avatar_structure)
- the garments that must be applied to a full-body didimo (--garment)
- the selected body gender for the didimo (--gender)

Input type accepts:
- photo
- rgbd (currently only tested with Apple depth images)

Please check all the options and accepted values using the command below.

```bash
didimo new --help
```

##### 4. Generate a package with hairs deformed for the newly generated didimo

Now that we have a didimo package, we may generate a package with Didimo's default set of hairs.

```bash
didimo execute hairsdeform <path to the didimo package>
```

##### 5. Explore

You can list your didimos with:

```bash
didimo list
```

To list the demo didimos use:

```bash
didimo list-demo-didimos
```

For more help, check the documentation on each command with the `--help` option.

### 4. Batch processing

The Didimo CLI supports batch processing of photo inputs automatically. Simply provide a path to a directory containing the input files and all files with be processed.
Alternatively, you can point to a zip file containing the input files.

```bash
didimo new photo /path_to_batch_input_files
```

Currently, only photo input is supported by batch processing.

### Getting an API Key

Go to the [Customer Portal](https://app.didimo.co) and register for an account.

Make sure that you tick the "Developer Account" checkbox in order to unlock
the "Developers" section on the sidebar.

After that, go to "Developers" > "Applications" and create an Application and
an API Key. Copy the information and paste on a text editor in order to
see every detail of your credentials
