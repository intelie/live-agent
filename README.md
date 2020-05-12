Live Agent
----------

Coordinates the execution of processes which interact with Intelie Live and simplifies their deployment.

Processes are implemented inside modules, segmented by its goal. The existing processes can be found at `live_agent/modules`

Each module can have:
- `datasources`: Process which generates and send events to live
- `monitors`: Processes which respond to events generated by queries
- `logic_adapters`: Classes which handle messages received by the chatbot

A `DDA` module should expose a `PROCESSES` dictionary, listing all processes it provides.
A process is started by a function (usually named `start`) which accepts two parameters:
- `settings`: a dictionary of the settings for this process;
- `kwargs`: a dictionary of extra parameters provided by `live-agent`'s runtime to this process.

The set of active modules (among other things) is defined using a settings file.
The module `chatbot` includes an example settings file.

`live-agent` requires python 3.7 or newer.


## Usage

```shell
# 1- Create a virtualenv using your preferred tool

# 2- Activate the virtualenv

# 3- Install live-agent (you should use a requirements.txt file to manage your dependencies)
(virtualenv)$ pip install live-agent[chatbot] --trusted-host pypi.intelie

# 4- Bootstrap a new agent
(virtualenv)$ create-agent
Creating the agent files:
- Creating "README.md"
- Creating "settings.json"
- Creating folder "tools"
- Creating folder "modules"
- Creating "modules/__init__.py"
Adding project settings:
- Creating "dev-requirements.txt"
- Creating "pyproject.toml"
- Creating ".pre-commit-config.yaml"
done

# 5- Create the initial structure for each of your agent's modules
(virtualenv)$ add-agent-module example --empty
Creating the module "example"
- Creating folder "modules"
- Creating folder "modules/example"
- Creating folder "modules/example/logic_adapters"
- Creating folder "modules/example/monitors"
- Creating folder "modules/example/datasources"
done

# 5.1- Or, use a sample module as reference
(virtualenv)$ add-agent-module example
Creating the module "example"
- Creating folder "modules"
- Removing old folder "modules/example"
- Creating folder "modules/example" with example code

The module "example" contains a "requirements.txt" file
Make sure that these dependencies are added to the main requirements

In order to run the agent with this module, execute:
agent-control console --settings=modules/example/settings_template.json
done

# 6- Implement the features you need on your modules and add them to settings.json
# Use the command `validate-settings` to validate the settings
$ validate-settings --settings=settings.json

# 7- Execute the agent
$ agent-control console --settings=settings.json

```


## Development

This project uses [black](https://github.com/psf/black) and [pre-commit](https://pre-commit.com/)


### Project setup:


```shell
# 1- Create a virtualenv

# 2- Activate the virtualenv

# 3- Install project requirements
$ pip install -r requirements.txt -r live_agent/modules/chatbot/requirements.txt

# 4- Check is your settings file seems to be correct
$ validate-settings --settings=modules/chatbot/settings_template.json

# 5- Execute the agent
$ ./live_agent/scripts/agent-control console --settings=modules/chatbot/settings_template.json
```

### Reading logs

This project uses `eliot` for logging. Eliot generates log messages as json objects,
which can be parsed by tools like `eliot-tree` and `eliot-prettyprint` or sent to Intelie Live.

The log file is stored at `/var/log/live-agent.log` by default. Make sure the user which will start the agent can write to this file.
The log messages are also sent to live, using the event_type `dda_log` by default.

```shell
# Reading the log with eliot-prettyprint
$ tail -f /var/log/live-agent.log | eliot-prettyprint

# Reading the log with eliot-tree (extra dependency, already on requirements.txt)
$ eliot-tree -l 0 /var/log/live-agent.log
```

### Building releases

In order to generate an installable package you will need to use `docker`.

- Install docker (check the documentation for your system: <https://docs.docker.com/install/>)
- Add your user to the group `docker`: `$ usermod -aG docker <username>`.
- Log off and log on again for the group to be recognized. (or you can simply `$ su - <username>` on your terminal)

The packager requires packages `fabric` and `virtualenv`. It will generate a rpm file for installation on the target system.

```shell
$ tools/package.sh c7
```

- `c7`: Build for centos7 and derivates (redhat 7, amazon linux 2, etc)


#### Testing the built packages

(As of now the testing is entirely manual)

##### In a container:

```shell
$ tools/test-envs/run_centos_container.sh 7

# Build dir will be available at /packages, so you can install and test
```

##### In a VM:

This allows to a more complete test, including running the app as a service

- Install VirtualBox and Vagrant (https://www.vagrantup.com/downloads.html)

```shell
# cd to `tools/test-envs/RedHat7`
$ cd tools/test-envs/RedHat7

# Starting VM:
$ vagrant up

# Connecting to the machine:
$ `vagrant ssh`

# To transfer files, copy to/from the `transf` subdirectory,
# it is automatically mapped as `/transf` at the test VM

# Stopping:

$ vagrant halt    # Stop
$ vagrant destroy # Completely erase the machine
```


#### Installing on the target system

```shell
$ rpm -Uvh <rpmfile>
```

### Publishing to pypi

```
# Build the packages
$ python setup.py egg_info sdist

# Validate the package
$ twine check dist/*

# Upload the package
$ twine upload dist/* -r intelie
```
