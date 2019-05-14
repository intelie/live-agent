#!/bin/bash

# Launcher script installed as /opt/intelie/live-agent/collect
#
# Starts the program in console mode
#
# Invocation: collect [settings file]

BASE_DIR=$(dirname $0)
SETTINGS_FILE="$1"

APP_ENTRY_POINT="${BASE_DIR}/lib/live_agent.py"
VIRTUALENV_ACTIVATE="${BASE_DIR}/pyenv/bin/activate"

# Simple validations on the environment and parameters
if [ "${SETTINGS_FILE}" == "" ]
then
    echo "Missing argument: settings file"
    exit 1
fi

if [ ! -f "${SETTINGS_FILE}" ]
then
    echo "Invalid settings file: ${SETTINGS_FILE}"
    exit 1
fi

if [ ! -f ${APP_ENTRY_POINT} ]
then
    echo "Entry point not found: ${APP_ENTRY_POINT}"
    exit 1
fi
if [ ! -f ${VIRTUALENV_ACTIVATE} ]
then
    echo "Virtualenv not found: ${VIRTUALENV_ACTIVATE}"
    exit 1
fi

source ${VIRTUALENV_ACTIVATE}
if [ $? -ne 0 ]
then
    exit 2
fi

python ${APP_ENTRY_POINT} console "${SETTINGS_FILE}"
