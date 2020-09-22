from setuptools import setup

pkg_vars = {}

with open('cli/_version.py') as f:
    exec(f.read(), pkg_vars)
setup(
    name="didimo-cli",
    version=pkg_vars["__version__"],
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
