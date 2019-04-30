Live Replayer
-------------

### Running in DEV:

_(Requirements: Python 2.7 , install dependencies from requirements.txt)_

    python src/main/generate_events.py console [settings_file]

    # Shortcut 1:
    ./run [settings_file]

    # Shortcut 2:
    ./run    # then select the settings file from the list

The project includes the following sample settings:

`src/main/settings.json` : Replays two sets of files concurrently


### Building

(requires packages `fabric` , `virtualenv`)

    tools/package.sh


### Testing the built packages

(As of now the testing is entirely manual)

#### In a container:

    tools/test-envs/run_centos_container.sh [6|7]
    # Build dir will be available at /packages, so you can install and test

#### In a VM:

This allows to a more complete test, including running the app as a service

- Install VirtualBox and Vagrant (https://www.vagrantup.com/downloads.html)

cd to `tools/test-envs/RedHat6` or `tools/test/RedHat7

Starting VM:

    vagrant up

Connecting to the machine:

    `vagrant ssh`

To transfer files, copy to/from the `transf` subdirectory,
it is automatically mapped as `/transf` at the test VM

Stopping:

    vagrant halt    # Stop
    vagrant destroy # Completely erase the machine
