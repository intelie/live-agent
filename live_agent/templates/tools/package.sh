#!/bin/bash

# Change the version when there are changes in the image or build entry point
DOCKER_IMAGE_c7=intelie/live-agent-build-c7:20190906

DOCKER_DIR=tools/builder
DOCKERFILE_c7=tools/builder/Dockerfile-c7

RELEASE="$1"
VERSION="$2"

. $(dirname $0)/vars.sh

if [ "$VERSION" == "" ]
then
    # Tries to get from the tag name when running on Gitlab CI
    VERSION="$CI_COMMIT_REF_NAME"
fi

if [ "$VERSION" == "" ]
then
    VERSION=$(date +%Y%m%d%H%M%S)
fi

#######################################################################

if ! id -Gn | egrep '[\W]*docker[\W]*' >/dev/null
then
    echo "User must be on the 'docker' group to use the commands without sudo"
    exit 1
fi

if [ "$RELEASE" == "c7" ]
then
    BUILDER_IMAGE_TAG=${DOCKER_IMAGE_c7}
    DOCKERFILE=${DOCKERFILE_c7}
else
    echo "Invalid release [ ${RELEASE} ]. Must be one of [c7]"
    exit 1
fi

echo "LAUNCHING BUILDER FOR : ${VERSION}  ${RELEASE} , image=${BUILDER_IMAGE_TAG}"

docker inspect ${BUILDER_IMAGE_TAG}
if [ $? -eq 1 ]
then
    echo "Building image"

    docker build -t ${BUILDER_IMAGE_TAG} -f ${DOCKERFILE} ${DOCKER_DIR}

    if [ $? -ne 0 ]
        then
        >&2 echo "Could not create Build Image. Aborting"
        exit 1
    fi
fi

if [ ! -d ${BUILD_TEMP} ]
then
    mkdir ${BUILD_TEMP}
    if [ $? -ne 0 ]
        then
        >&2 echo "Could not create temp dir. Aborting"
        exit 1
    fi
fi

docker run --rm -it \
    -v ${PROJECT_ROOT}:/build \
    --add-host pypi.intelie:10.42.1.118 \
    --env VERSION=${VERSION} \
    --env RELEASE=${RELEASE} \
    ${BUILDER_IMAGE_TAG} \
    /build/tools/package_task.sh

if [ $? -ne 0 ]
    then
    >&2 echo "RPM Build failed"
    exit 1
fi

echo RPM available
ls -lh ${RPM_FINAL}/*.rpm
