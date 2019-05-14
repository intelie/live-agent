%define debug_package %{nil}
%global __os_install_post %{nil}

%define service_name    live-agent

Summary:        Intelie Live external agent
Name:           live-agent
Version:        %{version}
Release:        %{release}
License:        Intelie Commercial License
Vendor:         Intelie
Group:          Application/Util
BuildArch:      x86_64

Source:         live-agent-%{version}-%{release}.tar.gz

Prefix: /opt/intelie/live-agent

Requires: %{requiredPython}
AutoReqProv: no

%description
Replayer for LAS files

%prep
%setup -q -n %{name}-%{version}-%{release}

%build

%install
mkdir -p %{buildroot}%{prefix}
cp -r * %{buildroot}%{prefix}/

mkdir -p %{buildroot}/etc/init.d
ln -s -f %{prefix}/collect-daemon %{buildroot}/etc/init.d/%{service_name}
# TODO: Create a systemd service for RedHat7

%files
%attr(755, -, -) %{prefix}/collect
%attr(755, -, -) %{prefix}/collect-daemon
%{prefix}/lib
%{prefix}/pyenv
%{prefix}/sample_settings.json
/etc/init.d/%{service_name}

%clean
rm -rf %{buildroot}

%post
if [ $1 == 1 ]; then
    # enable and start service
    /sbin/chkconfig --add %{service_name}
    /sbin/chkconfig %{service_name} on
fi
exit 0

%preun
# stop service (update and uninstall)
/sbin/service %{service_name} stop >/dev/null 2>&1
if [ $1 == 0 ]; then
    # only uninstall
    /sbin/chkconfig --del %{service_name}
fi
exit 0


%changelog
