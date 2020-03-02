Live Agent
----------

Coordinates the execution of processes which interact with Intelie Live and simplifies their deployment.

Processes are implemented inside modules, segmented by its objective, The existing processes can be found at `src/modules`
Each module can have:
- `datasources`: Process which send events to live
- `monitors`: Processes which respond to the events generateb by queries
- `logic_adapters`: Classes which handle messages received by the chatbot

The set of active modules is defined using a settings file.
The project includes the following sample settings:

- `src/main/settings/settings-replay.json` : Continuously replays MDT job files for two wells
- `src/main/settings/settings-pretest.json` : Pretest monitor
- `src/main/settings/settings-sampling.json` : Focused sampling monitor
- `src/main/settings/settings-monitor.json` : Pretest, sampling and flowrate monitors
- `src/main/settings/settings-chatbot.json` : Chatbot
- `src/main/settings/settings.json` : All features enabled


## Project setup:

Requires python 3.6 or newer

```shell
# 1- Create a virtualenv

# 2- Activate the virtualenv

# 3- Install project requirements
$ pip install -r requirements.txt -c constraints.txt

# 4- Check is your settings file seems to be correct
$ check_live_features --settings=<settings_file>

# 5- Execute the agent
$ ./run  # then select the settings file from the list

# 5.1- You can also start the agent with an specific settings file
$ ./run <settings_file>

# 5.2- Or, execute the agent script directly
$ python src/main/live_agent.py console <settings_file>

```

## Reading logs

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


## Building

In order to generate an installable package you will need to use `docker`.

- Install docker (check the documentation for your system: <https://docs.docker.com/install/>)
- Add your user to the group `docker`: `$ usermod -aG docker <username>`.
- Log off and log on again for the group to be recognized. (or you can simply `$ su - <username>` on your terminal)

The packager requires packages `fabric` and `virtualenv`. It will generate a rpm file for installation on the target system.

```shell
$ tools/package.sh c7
```

- `c7`: Build for centos7 and derivates (redhat 7, amazon linux 2, etc)


### Testing the built packages

(As of now the testing is entirely manual)


#### In a container:

```shell
$ tools/test-envs/run_centos_container.sh 7

# Build dir will be available at /packages, so you can install and test
```

#### In a VM:

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


## Installing on the target system

```shell
$ rpm -Uvh <rpmfile>
```
