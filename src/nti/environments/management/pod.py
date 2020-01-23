import os
import json

import subprocess

from zope import component
from zope import interface

from .interfaces import IEnvironmentProvisioner
from .interfaces import IProvisionEnvironmentTask
from .interfaces import ISettings

from .tasks import AbstractTask
from .tasks import mock_task

logger = __import__('logging').getLogger(__name__)


def _mock_init_pod_env(*args, **kwargs):
    return mock_task(*args, **kwargs)


def _init_pod_env(task, site_id, site_name, dns_name):
    provisioner = component.getUtility(IEnvironmentProvisioner)
    return provisioner.provision_environment(site_id, site_name, dns_name)

def _pod_root_init_log(podid):
    settings = component.getUtility(ISettings)['pods']
    return os.path.join(settings['root_dir'], podid, settings['pod_logs_dir'], 'init.log')
    

@interface.implementer(IEnvironmentProvisioner)
class EnvironmentProvisioner(object):

    def __init__(self, script_name):
        self.script_name = script_name

    def provision_environment(self, site_id, site_name, dns_name):
        logger.info('Provisioning environment using %s for site=(%s) name=(%s) dns_name=(%s)',
                    self.script_name, site_id, site_name, dns_name)
        completed_process = subprocess.run([self.script_name, site_id, site_name, dns_name],
                                           check=False,
                                           capture_output=True,
                                           encoding='utf-8',
                                           shell=True)
    
        # Capture any logging on stderr and write it to our log file
        # This probably shouldn't fail if setup actually succeeded. Do
        # we want a failure here to fail the setup and the entire job?
        with open(_pod_root_init_log(site_id), 'x') as f:
            f.write(completed_process.stderr)

        for line in completed_process.stderr.splitlines():
            logger.debug('%s for site=(%s) produced output: %s', self.script_name, site_id, line)

        logger.info('Provisioning environment for site=(%s) completed with code=(%i)',
                    site_id, completed_process.returncode)

        # Check out return code which will raise if things failed
        completed_process.check_returncode()

        stdout = completed_process.stdout
        assert stdout
        return json.loads(stdout)

def _provisioner_factory():
    settings = component.getUtility(ISettings)
    return EnvironmentProvisioner('init_pod_environment')

def _mock_provisioner_factory():
    settings = component.getUtility(ISettings)
    return EnvironmentProvisioner('nti_environments_management_mock_init')


@interface.implementer(IProvisionEnvironmentTask)
class ProvisionEnvironmentTask(AbstractTask):

    NAME = 'provision_env'
    TC = _init_pod_env

    def __call__(self, site_id, site_name, dns_name):
        return self.task.apply_async((site_id, site_name, dns_name, ))


@interface.implementer(IProvisionEnvironmentTask)
class MockProvisionEnvironmentTask(ProvisionEnvironmentTask):

    NAME = 'mock_' + ProvisionEnvironmentTask.NAME
