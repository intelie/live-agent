import os
from setuptools import setup, find_packages

__all__ = ["setup"]


def read_file(filename):
    """Read a file into a string"""
    path = os.path.abspath(os.path.dirname(__file__))
    filepath = os.path.join(path, filename)
    try:
        return open(filepath).read()
    except IOError:
        return ""


def get_readme():
    """Return the README file contents. Supports text,rst, and markdown"""
    for name in ("README", "README.rst", "README.md"):
        if os.path.exists(name):
            return read_file(name)
    return ""


def install_requires(module=None):
    if module:
        filepath = f"./live_agent/modules/{module}/"
    else:
        filepath = ""

    requirements = read_file(f"{filepath}requirements.txt")
    return requirements


setup(
    name="live_agent",
    version="0.10.6",
    description="A framework for implementing agents which interact with the Intelie LIVE platform",
    long_description=get_readme(),
    long_description_content_type="text/markdown",
    packages=find_packages(),
    include_package_data=True,
    scripts=[
        "live_agent/scripts/agent-control",
        "live_agent/scripts/create-agent",
        "live_agent/scripts/add-agent-module",
        "live_agent/scripts/validate-settings",
    ],
    url="https://github.com/intelie/live-agent",
    author="Vitor Mazzi",
    author_email="vitor.mazzi@intelie.com.br",
    install_requires=[
        "live-client>=0.6.1",
        "eliot>=1.12.0",
        "eliot-tree>=19.0.0",
        "setproctitle>=1.1.10",
        "dill>=0.3.1.1",
        "requests>=2,<3",
    ],
    extras_require={
        "chatbot": [
            "ChatterBot==1.0.5",
            "chatterbot-corpus==1.2.0",
            "Jinja2==2.10.1",
            "pytz>=2019.2",
            "python-dateutil>=2.7,<2.8",
            "PyYAML>=3.12,<4.0",
        ],
        "las": ["lasio==0.23", "pandas==0.24.2", "scikit-learn>=0.20"],
    },
    zip_safe=False,
    python_requires=">=3.7",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: POSIX :: Linux",
        "Development Status :: 4 - Beta",
        "Topic :: Software Development :: Libraries :: Application Frameworks",
    ],
)
