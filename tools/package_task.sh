#!bin/bash
# This is the actual package task, to be invoked from the container.


PROJECT_ROOT=/build
BUILD_TEMP=${PROJECT_ROOT}/temp
VIRTUALENV_PATH=/opt/intelie/live-agent/pyenv

LAUNCHER_SCRIPT_NAME="collect"
DAEMON_SCRIPT_NAME="collect-daemon"
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

if [ "$RELEASE" == "c6" ]
then
    REQUIRED_PYTHON=intelie-python27
    VIRTUALENV_CMD=/opt/intelie/runtime/python27/bin/virtualenv
elif [ "$RELEASE" == "c7" ]
then
    REQUIRED_PYTHON="python >= 2.7.0, python <= 2.7.99999"
    VIRTUALENV_CMD="virtualenv -p python2.7"
else
    echo "Invalid release [ ${RELEASE} ]. Must be one of [c6, c7]"
    exit 1
fi

##########
echo "[STEP 1] PREPARE VIRTUALENV"

test -d ${BUILD_TEMP}
assert_ok $?

${VIRTUALENV_CMD} --no-site-packages --unzip-setuptools ${VIRTUALENV_PATH}
assert_ok $?

${VIRTUALENV_PATH}/bin/pip install -U pip
assert_ok $?

${VIRTUALENV_PATH}/bin/pip install -r ${PROJECT_ROOT}/requirements.txt
assert_ok $?

##########
echo "[STEP 2] COPY RESOURCES TO RELEASE"

RELEASE_DIR=${RPM_BUILD_ROOT}/${PACKAGE_FULL_NAME}

rm -rf ${RPM_BUILD_ROOT}

mkdir -p ${RELEASE_DIR}/lib
assert_ok $?

cp -r ${VIRTUALENV_PATH} ${RELEASE_DIR}/
assert_ok $?

# Copy python files from the src root and up to une level of subdir
# This is enough for simple projects
cp -v ${PROJECT_ROOT}/src/main/*.py ${RELEASE_DIR}/lib/
assert_ok $?

for f in ${PROJECT_ROOT}/src/main/*/*.py
do
    dir=$(dirname $f)
    dir=$(basename $dir)
    if [ ! -d ${RELEASE_DIR}/lib/${dir} ]
    then
        mkdir ${RELEASE_DIR}/lib/${dir}
        assert_ok $?
    fi
    cp -v $f ${RELEASE_DIR}/lib/${dir}/
done

cp -v ${PROJECT_ROOT}/tools/launcher.sh ${RELEASE_DIR}/${LAUNCHER_SCRIPT_NAME}
assert_ok $?

cp -v ${PROJECT_ROOT}/tools/launcher-daemon-control.sh ${RELEASE_DIR}/${DAEMON_SCRIPT_NAME}
assert_ok $?

cp -v ${PROJECT_ROOT}/src/main/settings.json ${RELEASE_DIR}/sample_settings.json
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
