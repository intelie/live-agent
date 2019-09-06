Live Agent
----------

## Project setup:

Requires python 3.6 or newer

```shell
# 1- Create a virtualenv

# 2- Activate the virtualenv

# 3- Install project requirements
$ pip install -r requirements.txt

# 4- Execute the application in one of the modes below:

# 4.1- Direct execution
$ python src/main/live_agent.py console [settings_file]

# 4.2- Shortcut defining the settings file
$ ./run [settings_file]

# 4.3- Shortcut without defining the settings file
$ ./run  # then select the settings file from the list
```

The project includes the following sample settings:

- `src/main/settings-replay.json` : Continuously replays MDT job files for two wells
- `src/main/settings-pretest.json` : Pretest monitor
- `src/main/settings-sampling.json` : Focused sampling monitor
- `src/main/settings-monitor.json` : Pretest, sampling and flowrate monitors
- `src/main/settings-chatbot.json` : Chatbot
- `src/main/settings.json` : All features enabled


## Reading logs

This project uses `eliot` for logging. Eliot generates log messages as json objects,
which can be parsed by tools like `eliot-tree` and `eliot-prettyprint` or sent to Intelie Live.

The log file is stored at `/var/log/live-agent.log` by default. When starting this tool from the
console the log is stored at `/tmp/live-agent.log`.
The log messages are also sent to live, using the event_type `dda_log` by default.

```shell
# Reading the log with eliot-prettyprint
$ tail -f /tmp/live-agent.log | eliot-prettyprint

# Reading the log with eliot-tree (extra dependency, already on requirements.txt)
$ eliot-tree -l 0 /tmp/live-agent.log
```


## Building

Requires packages `fabric` and `virtualenv`, will generate a rpm file for installation on the target system

```shell
$ tools/package.sh c7
```

- `c7`: Build for centos7 and derivates (redhat 7, amazon linux 2, etc)


### Testing the built packages

(As of now the testing is entirely manual)


#### In a container:

```shell
$ tools/test-envs/run_centos_container.sh [6|7]

# Build dir will be available at /packages, so you can install and test
```

#### In a VM:

This allows to a more complete test, including running the app as a service

- Install VirtualBox and Vagrant (https://www.vagrantup.com/downloads.html)

```shell
# cd to `tools/test-envs/RedHat6` or `tools/test/RedHat7`
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
