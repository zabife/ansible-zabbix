import os
import pytest

import testinfra.utils.ansible_runner

from ansible.template import Templar
from ansible.parsing.dataloader import DataLoader

testinfra_hosts = testinfra.utils.ansible_runner.AnsibleRunner(
    os.environ['MOLECULE_INVENTORY_FILE']).get_hosts('all')


@pytest.fixture(scope='module')
def ansible_vars(host):
    """
    Return a dict of the variable defined in the role tested or the inventory.
    Ansible variable precedence is respected.
    """
    defaults_files = "file=../../defaults/main.yml"
    vars_files = "file=../../vars/main.yml"

    host.ansible("setup")
    host.ansible("include_vars", defaults_files)
    host.ansible("include_vars", vars_files)
    all_vars = host.ansible.get_variables()
    all_vars["ansible_play_host_all"] = testinfra_hosts
    templar = Templar(loader=DataLoader(), variables=all_vars)
    return templar.template(all_vars, fail_on_undefined=False)


def test_hosts_file(host):
    f = host.file('/etc/hosts')

    assert f.exists
    assert f.user == 'root'
    assert f.group == 'root'


def test_zabbiserver_running_and_enabled(Service, SystemInfo):
    if SystemInfo.distribution == 'centos':
        zabbix = Service("zabbix-server")
        assert zabbix.is_enabled
        assert zabbix.is_running


@pytest.mark.parametrize("server, redhat, debian", [
        ("zabbix-server-pgsql", "zabbix-web-pgsql", "zabbix-frontend-php"),
        ("zabbix-server-mysql", "zabbix-web-mysql", "zabbix-frontend-php"),
])
def test_zabbix_package(host, server, redhat, debian):
    host = host.backend.get_hostname()
    host = host.replace("-centos", "")
    host = host.replace("-debian", "")
    host = host.replace("-ubuntu", "")

    if host == server:
        if host.system_info.distribution in ['debian', 'ubuntu']:
            zabbix_web = host.package(debian)
            assert zabbix_web.version.startswith("1:4.2")
        elif host.system_info.distribution == 'centos':
            zabbix_web = host.package(redhat)
            assert zabbix_web.version.startswith("4.2")
            assert zabbix_web.is_installed


def test_zabbix_server_dot_conf(File):
    zabbix_server_conf = File("/etc/zabbix/zabbix_server.conf")
    assert zabbix_server_conf.user == "zabbix"
    assert zabbix_server_conf.group == "zabbix"
    assert zabbix_server_conf.mode == 0o640

    assert zabbix_server_conf.contains("ListenPort=10051")
    assert zabbix_server_conf.contains("DBHost=localhost")
    assert zabbix_server_conf.contains("DebugLevel=3")


def test_zabbix_include_dir(File):
    zabbix_include_dir = File("/etc/zabbix/zabbix_server.conf.d")
    assert zabbix_include_dir.is_directory
    assert zabbix_include_dir.user == "zabbix"
    assert zabbix_include_dir.group == "zabbix"
# assert zabbix_include_dir.mode == 0o644


def test_zabbix_web(host):
    zabbix_web = host.file("/etc/zabbix/web/zabbix.conf.php")

    if host.system_info.distribution in ['debian', 'ubuntu']:
        assert zabbix_web.user == "www-data"
        assert zabbix_web.group == "www-data"
    elif host.system_info.distribution == 'centos':
        assert zabbix_web.user == "apache"
        assert zabbix_web.group == "apache"
    assert zabbix_web.mode == 0o640


@pytest.mark.usefixtures('ansible_vars')
def test_zabbix_api(host):
    my_host = host.ansible.get_variables()
    print(host.ansible.get_variables())
    zabbix_url = str(my_host['zabbix_url'])
    hostname = 'http://' + zabbix_url + '/api_jsonrpc.php'
    post_data = '{"jsonrpc": "2.0", "method": "user.login", "params": { \
        "user": "Admin", "password": "zabbix" }, "id": 1, "auth": null}'
    headers = 'Content-Type: application/json-rpc'
    command = "curl -XPOST -H '" + str(headers) + "' -d '" \
        + str(post_data) + "' '" + hostname + "'"

    cmd = host.run(command)
    assert '"jsonrpc":"2.0","result":"' in cmd.stdout
