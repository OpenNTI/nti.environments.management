import os
import json
import time

import subprocess

from zope import component
from zope import interface

from .interfaces import IEnvironmentProvisioner
from .interfaces import IProvisionEnvironmentTask
from .interfaces import ISettings

from .tasks import AbstractTask
from .tasks import mock_task

logger = __import__('logging').getLogger(__name__)

_MAX_SLEEP = 120

def _mock_init_pod_env(task, site_id, site_name, dns_name, customer_name, customer_email):
    """
    A mock task that simulates an environment pod being spun up.
    We let the task caller influence the behaviour of the task by the domain name.
    We split the subdomain portion by '-'. The last portion, if numeric, defines
    the amount of time this task should take (in seconds) maxed out at 120. If any
    part of the split domain contains the word 'Error' an exception will be raised
    after sleeping.
    """

    subdomain = dns_name.split('.')[0]
    parts = subdomain.split('-')
    try:
        numeric = int(parts[-1])
        # Normalize between 10 and _MAX_SLEEP seconds
        b = _MAX_SLEEP
        a = 10
        sleep = ((b - a)*(numeric/10000)) + a
    except (TypeError, ValueError):
        sleep = 10

    should_raise = bool(tuple(filter(lambda x: 'error' in x, parts)))

    logger.info('Mock pod init will finish in %i seconds with success=%s', sleep, should_raise)
    time.sleep(sleep)

    if should_raise:
        raise Exception('Mock setup failed')

    return 'host1.dev', '/dataserver2/@@accept-site-invitation?code=mockcode'


def _init_pod_env(task, site_id, site_name, dns_name, customer_name, customer_email):
    provisioner = component.getUtility(IEnvironmentProvisioner)
    result = provisioner.provision_environment(site_id, site_name, dns_name, customer_name, customer_email)
    return result['host_system'], result['admin_invitation']

def _pod_root_init_log(podid):
    settings = component.getUtility(ISettings)['pods']
    return os.path.join(settings['root_dir'], podid, settings['pod_logs_dir'], 'init.log')
    

@interface.implementer(IEnvironmentProvisioner)
class EnvironmentProvisioner(object):

    def __init__(self, script_name):
        self.script_name = script_name

    def provision_environment(self, site_id, site_name, dns_name, customer_name, customer_email):
        logger.info('Provisioning environment using %s for site=(%s) name=(%s) dns_name=(%s)',
                    self.script_name, site_id, site_name, dns_name)
        completed_process = subprocess.run([self.script_name, site_id, site_name, dns_name, customer_name, customer_email],
                                           check=False,
                                           stderr=subprocess.PIPE,
                                           stdout=subprocess.PIPE,
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
        assert stdout is not None
        return json.loads(stdout)

def _provisioner_factory():
    settings = component.getUtility(ISettings)
    return EnvironmentProvisioner('init_pod_environment')

@interface.implementer(IProvisionEnvironmentTask)
class ProvisionEnvironmentTask(AbstractTask):

    NAME = 'provision_env'
    TC = _init_pod_env
    QUEUE = 'any_host'

    def __call__(self, site_id, site_name, dns_name, customer_name, customer_email):
        return self.task.apply_async((site_id, site_name, dns_name, customer_name, customer_email))


@interface.implementer(IProvisionEnvironmentTask)
class MockProvisionEnvironmentTask(ProvisionEnvironmentTask):

    NAME = 'mock_' + ProvisionEnvironmentTask.NAME
    TC = _mock_init_pod_env
