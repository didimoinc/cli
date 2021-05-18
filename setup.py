from setuptools import setup
import pathlib

pkg_vars = {}
here = pathlib.Path(__file__).parent.resolve()

with open(here / 'cli/_version.py', encoding='utf-8') as f:
    exec(f.read(), pkg_vars)

long_description = (here / 'README.md').read_text(encoding='utf-8')

setup(
    name="didimo-cli",
    version=pkg_vars["__version__"],
    description="Command-line interface to interact with Didimo API",
    long_description=long_description,
    long_description_content_type='text/markdown',
    url="https://github.com/didimoinc/cli",
    project_urls={
        'Bug Reports': 'https://github.com/didimoinc/cli/issues',
        'Source': 'https://github.com/didimoinc/cli',
    },
    author="Didimo, Inc.",
    author_email="support@didimo.co",
    keywords='cli, didimo, api',
    license='Apache 2.0',
    classifiers=[
        'License :: OSI Approved :: Apache Software License',
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'Topic :: Games/Entertainment',
        'Topic :: Multimedia :: Graphics',
        'Programming Language :: Python :: 3'
    ],
    packages=["cli"],
    include_package_data=True,
    install_requires=[
      "click",
      "requests"
    ],
    entry_points="""
        [console_scripts]
        didimo=cli.cli:cli
    """
)
