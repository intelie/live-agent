#!/bin/bash
# chkconfig: 345 99 01
# description: BOP Video Collector

# Service Launcher script installed as /opt/intelie/live-replayer/collect-daemon
#
# Controls the execution of the program as a daemon
#
# Invocation: collect-daemon [start|stop|restart|status]

SCRIPT_PATH=$(readlink -f $0)   # We may be running through a symlink. Resolve actual script
BASE_DIR=$(dirname ${SCRIPT_PATH})

SETTINGS_FILE="${BASE_DIR}/settings.json"

APP_ENTRY_POINT="${BASE_DIR}/lib/live_agent.py"
VIRTUALENV_ACTIVATE="${BASE_DIR}/pyenv/bin/activate"

PID_FILE=/var/run/live-replayer.pid

COMMAND="$1"

function check_status() {
    if [ ! -f "${PID_FILE}" ]
    then
        echo "Process not running"
        exit 1
    fi

    pid="$(cat ${PID_FILE})"
    if [ "$pid" == "" ]
    then
        echo "Pid file ${PID_FILE} is empty! Was it changed from outside?"
        exit 1
    fi

    ps -fp ${pid}
    if [ $? -eq 0 ]
    then
        echo "Process is running"
        exit 0
    else
        echo "Process not running (PID file found - unexpectedly killed?)"
        exit 1
    fi
}

# Simple validations on the environment and parameters
if [ "${COMMAND}" != "start" -a "${COMMAND}" != "stop" -a "${COMMAND}" != "restart" -a "${COMMAND}" != "status" ]
then
    echo "Invalid argument: use one of [start | stop | restart | status]"
    exit 1
fi

if [ "${COMMAND}" == "status" ]
then
    check_status
fi

if [ ! -f "${SETTINGS_FILE}" ]
then
    echo "Settings file does not exist: ${SETTINGS_FILE}"
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

python ${APP_ENTRY_POINT} ${COMMAND} "${SETTINGS_FILE}"
