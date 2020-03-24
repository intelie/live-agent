#!/bin/bash

if [ "$1" != "6" -a "$1" != "7" ]
then
	echo "Missing or invalid parameter: CentOS version = '6' or '7'"
	exit 1
fi

ver=$1

script_dir=$(dirname $0)
. ${script_dir}/../vars.sh

if [ ! -d "${BUILD_TEMP}" ]
then
	echo "BUILD_TEMP not set or does not exist: ${BUILD_TEMP}"
	exit 1
fi

docker run --rm -it -v $(readlink -f ${BUILD_TEMP}):/packages centos:${ver} /bin/bash

