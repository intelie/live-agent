#!bin/bash
# This is the actual package task, to be invoked from the container.

PROJECT_ROOT=/build
BUILD_TEMP=${PROJECT_ROOT}/temp
VIRTUALENV_PATH=/opt/intelie/live-agent/pyenv

DAEMON_SCRIPT_NAME="manage-agent"
PACKAGE_NAME="live-agent"

RPM_BUILD_ROOT=${BUILD_TEMP}/rpmbuild

PACKAGE_FULL_NAME=${PACKAGE_NAME}-${VERSION}-${RELEASE}

######################################################################
function assert_ok() {
    if [ $1 -ne 0 ]
    then
        >&2 echo "The previous command returned with error. Aborting"
        exit 1
    fi
}

echo "BUILDING VERSION : ${VERSION}  ${RELEASE}"

#########
# Validations and definitions
if [ "${VERSION}" == "" -o "${RELEASE}" == "" ]
then
    echo "Environment vars VERSION and RELEASE must be set. Check if proper invocation procedure is being used"
    exit 1
fi

if [ "$RELEASE" == "c7" ]
then
    REQUIRED_PYTHON="python3 >= 3.6.0, python <= 4.0"
    VIRTUALENV_CMD="/usr/bin/python3.7 -m venv"
else
    echo "Invalid release [ ${RELEASE} ]. Must be one of [c7]"
    exit 1
fi

##########
echo "[STEP 1] PREPARE VIRTUALENV"

test -d ${BUILD_TEMP}
assert_ok $?

${VIRTUALENV_CMD} ${VIRTUALENV_PATH}
assert_ok $?

${VIRTUALENV_PATH}/bin/pip install -U pip
assert_ok $?

${VIRTUALENV_PATH}/bin/pip install -r requirements.txt -c constraints.txt --trusted-host pypi.intelie
assert_ok $?

##########
echo "[STEP 2] COPY RESOURCES TO RELEASE"

RELEASE_DIR=${RPM_BUILD_ROOT}/${PACKAGE_FULL_NAME}

rm -rf ${RPM_BUILD_ROOT}

mkdir -p ${RELEASE_DIR}/modules
assert_ok $?

# Copy the local modules to the release folder
cp -R ${PROJECT_ROOT}/modules/* ${RELEASE_DIR}/modules/
assert_ok $?

cp -r ${VIRTUALENV_PATH} ${RELEASE_DIR}/
assert_ok $?

cp -v ${PROJECT_ROOT}/tools/launcher-daemon-control.sh ${RELEASE_DIR}/${DAEMON_SCRIPT_NAME}
assert_ok $?

cp -v ${PROJECT_ROOT}/live_agent/settings/settings.json ${RELEASE_DIR}/sample_settings.json
assert_ok $?

##########
echo "[STEP 3] CREATE RPM"

mkdir -p ${RPM_BUILD_ROOT}/{SOURCES,SPECS,BUILD,RPMS,SRPMS}
assert_ok $?

tar -czf ${RPM_BUILD_ROOT}/SOURCES/${PACKAGE_FULL_NAME}.tar.gz -C ${RPM_BUILD_ROOT} ${PACKAGE_FULL_NAME}
assert_ok $?

rpmbuild \
  --define="version ${VERSION}" \
  --define="release ${RELEASE}" \
  --define="requiredPython ${REQUIRED_PYTHON}" \
  --define="%_topdir ${RPM_BUILD_ROOT}" \
  -bb ${PROJECT_ROOT}/tools/rpm.spec

assert_ok $?

RPM_FINAL=${BUILD_TEMP}/rpm-${RELEASE}

rm -rf ${RPM_FINAL}
mkdir ${RPM_FINAL}
assert_ok $?

cp ${RPM_BUILD_ROOT}/RPMS/*/*.rpm ${RPM_FINAL}/
