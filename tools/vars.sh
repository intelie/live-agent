#!/bin/bash

# Go from the current dir up in the hierarchy until the project root is found
dir=$(dirname $0)
while [ ! -f "${dir}/requirements.txt" ]
do
    dir=$(dirname $dir)
done

PROJECT_ROOT=$(readlink -f $dir)

BUILD_TEMP="${PROJECT_ROOT}/temp"
RPM_FINAL=${PROJECT_ROOT}'/temp/rpm-*'