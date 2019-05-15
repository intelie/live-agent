Live Agent
----------

### Project setup:

Requires python 2.7, 3.4 or newer

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

- `src/main/settings-monitor.json` : Generates notifications on messenger whenever the values for some defined metrics are updated too frequently
- `src/main/settings-replay.json` : Continuously replays MDT job files for two wells
- `src/main/settings.json` : Replay and monitor


### Building

Requires packages `fabric` and `virtualenv`, will generate a rpm file for installation on the target system

```shell
$ tools/package.sh [c6|c7]
```

- `c6`: Build for centos6 and derivates (red hat 6, amazon linux, etc)
- `c7`: Build for centos7 and derivates (redhat 7, amazon linux 2, etc)


### Installing on the target system

```shell
$ rpm -Uvh <rpmfile>
```

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
