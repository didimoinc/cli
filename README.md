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
  bulk                              Perform bulk requests related operations
  clear-cache                       Clears cache and exit
  config                            Get or set configuration
  delete                            Delete a didimo
  download                          Download a didimo
  execute                           Execute on-demand features on didimos
  generation-template               Perform didimo generation template management operations
  init                              Initializes configuration
  inspect                           Get details of didimos
  list                              List didimos
  list-demo-didimos                 List demo didimos
  metadata                          Perform metadata related operations on didimos
  new                               Create a didimo
  status                            Get status of didimos
  version                           Print CLI version and exit
  version-api                       Print API/DGP version and exit
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
didimo new <path to the photo> photo 
```

The CLI waits for the didimo to be created and downloads the result in a zip
file.

Generating a didimo may include several options, as described on our developer portal.

The tool allows the selection of the avatar structure (--avatar-structure), for which it currently accepts full-body or head-only (default) options. For full-body requests, some extra parameters are available:
- the definition of the body pose (--body-pose);
- the definition of the garments (--garment);
- the definition of a gender (--gender).

Didimo CLI currently accepts the following features (-f):
- oculus_lipsync
- simple_poses
- arkit
- aws_polly

The CLI accepts following output formats (-p):
- glTF
- FBX

In addition to those, it also accepts:
- the definition of a profile (--profile), which will drive the output texture files dimensions and formats;
- the definition of a default hair or baseball cap, from our collection of hairstyles (--hair).

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
didimo new /path_to_batch_input_files photo
```

Currently, only photo input is supported by batch processing.

This feature will result in standard requests to generate didimos so you should consider bulk processing if you intend to generate a large number of didimos in one pass (please read the following section for more information on bulk processing).

### 5. Bulk processing

The Didimo CLI supports bulk processing of photo inputs automatically. Simply provide a path to a ZIP file containing the input files and all files will be processed as a bulk request.

```bash
didimo bulk new didimos /path_to_batch_input_files photo
```

An important distinction between batch and bulk processing is that the batch process is controlled by the client application, which makes standard requests to generate didimos, while the bulk request handles the process as a whole. Resulting in a quicker registration of the job but may result on a lower turn-around-time (TAT) as the package is processed in the background, with lower priority. This feature is intended to be used in the generation of a large number of didimos without
blocking the user interface.

You can perform queries to assess the status of the processing of bulk requests, using the get command that outputs relevant progress information of each individual item.

```bash
didimo bulk get didimos bulk_uuid
```

You can also query all the existing bulk requests on your account with the list command.

```bash
didimo bulk list didimos
```

Currently, only photo input is supported by bulk processing.

### 6. Didimo generation templates

The commands related to didimo generation support the use of templates to facilitate the use and prevent unintended errors while generating your didimos. We have predefined templates which are set at system level and you can generate your own. 

Use the following command to list available didimo generation templates.

```bash
didimo generation-templates list
```

You can add a new DGT, according to your current DGP signature, using the create command. Use the following command to get instructions on how to use it and see all the available features and options.

```bash
didimo generation-templates create -h
```

You will be able to use these templates as parameter on the commands:
  - "new" (to generate a new didimo): e.g. didimo new /path_to_batch_input_files --template templateCodename
  - "bulk" (to generate didimos in bulk): e.g. didimo bulk new didimos /path_to_batch_input_files --template templateCodename

You will still be able to override any template values if needed by providing the parameters as you normally would, and the remaining attributes will be fetched from the provided template.

NOTE: These templates need to be created for each DGP (didimo generation pipeline) signature if there are breaking changes to the DGP signature, but are shared across compatible DGP versions.

### Getting an API Key

Go to the [Customer Portal](https://app.didimo.co) and register for an account.

Make sure that you tick the "Developer Account" checkbox in order to unlock
the "Developers" section on the sidebar.

After that, go to "Developers" > "Applications" and create an Application and
an API Key. Copy the information and paste on a text editor in order to
see every detail of your credentials
