# Developing the CLI

### Quickstart
We use a virtualenv to develop the CLI to make it easier to test the code in a
more isolated environment and to not polute our system.

Start by creating a virtualenv in the root of the repo. In this case, we
called it `cli-env`

```bash
virtualenv cli-env
```

After the virtualenv is created, you should see a `cli-env` folder with
python and pip executables along some helper functions to instruct your
shell that this is a virtualenv. This will change your current shell session
paths to this isolated environment.

```bash
. ./cli-env/bin/activate
```

Last step is to install the requirements. If you inspect the
[`requirements.txt`](requirements.txt) file, you can see that our package
is an editable one, which means that while developing, there's no need to
reinstall our package to have our changes, that is done automatically.

```bash
pip install -r requirements.txt
```

At this point, you're good to start developing the CLI. After you're done, you
can exit the virtualenv - restoring you shell session to the point before
entering the virutalenv - running the following command:

```bash
deactivate
```

### Code

We are using a conventional changelog format in order to automatically
generate a changelog.

Each commit message consists of a header, an optional body and an optional
footer. The header has a special format that includes a type and a subject:

```
<type>: <subject>
<BLANK LINE>
<body>
<BLANK LINE>
<footer>
```

Any line of the commit message should be no longer than 100 characters.
This allows the message to be easier to read on git tools.

The type should be one of the list:

- **feat**: A new feature
- **fix**: A bug fix
- **docs**: Documentation only changes
- **style**: Changes that do not affect the meaning of the code (white-space, formatting, missing semi-colons, etc)
- **refactor**: A code change that neither fixes a bug or adds a feature
- **perf**: A code change that improves performance
- **test**: Adding missing tests
- **chore**: Changes to the build process or auxiliary tools and libraries such as documentation generation

You can read more about our git commit convention at
[this link](https://github.com/conventional-changelog/conventional-changelog/blob/a5505865ff3dd710cf757f50530e73ef0ca641da/conventions/angular.md).

For the code itself, we heavily depend on the Click package. Please refer to
[Click Documentation](https://click.palletsprojects.com).

### Release

After adding new features or fixing bugs and you're ready to make a
release, it's time to update the [CHANGELOG.md](CHANGELOG.md) and
[README.md](README.md) files.

For the changelog, we use a tool
called [clog-cli](https://github.com/clog-tool/clog-cli).

After installing it, we can update the changelog running the tool
on the root of the repo:
```
clog --from <last version> --setversion <new version>
```

Also, update the link to install this new version
on the [README.md](README.md) file.
