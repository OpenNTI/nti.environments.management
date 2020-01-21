"""
A simulated environment setup task and accompanying script
entry point.
"""

import argparse
import os
import time
import subprocess
import json
import functools

from celery import group

from zope.component.hooks import setHooks

from zope.configuration import config
from zope.configuration import xmlconfig

from zope.dottedname import resolve as dottedname

from zope import interface

from .interfaces import IProvisionEnvironmentTask
from .interfaces import IDNSMappingTask
from .interfaces import IHaproxyBackendTask
from .interfaces import ISetupEnvironmentTask


class AbstractTask(object):

    NAME = None
    TC = None

    @classmethod
    def bind(cls, app):
        app.task(bind=True, name=cls.NAME)(cls.TC)

    def __init__(self, app):
        self.app = app

    @property
    def task(self):
        return self.app.tasks[self.NAME]

    

def setup_site(task, site_id, site_name, hostname, **options):
    """
    Given a site_id, site_name, and hostname spin up an environment.
    We expect the caller has validated all our input. We take responsibility
    for spinning things up.

    This is an asynchronous task we expect to be invoked on the host system
    for the new environment.
    """
    executable = os.path.join(os.environ.get('NTI_ONBOARDING_BIN', ''), 'nti_environments_managment_mock_init.sh')
    process = subprocess.Popen([executable, '5'],
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    return json.loads(stdout.decode('utf-8'))

@interface.implementer(IProvisionEnvironmentTask)
class ProvisionEnvironmentTask(AbstractTask):

    NAME = 'provision_env'
    TC = setup_site

    def __call__(self, site_id, site_name, dns_name):
        return self.task.apply_async((site_id, site_name, dns_name))


def mock_task(task, *args, **kwargs):
    time.sleep(kwargs.get('sleep', 60))
    return {'args': args,
            'kwargs': kwargs}


def mock_haproxy(*args, **kwargs):
    return mock_task(*args, **kwargs)

@interface.implementer(IHaproxyBackendTask)
class MockSetupHAProxyBackend(AbstractTask):

    NAME = 'create_haproxy_backend'
    TC = mock_haproxy

    def __call__(self, site_id, dns_name):
        return self.task.apply_async((site_id, dns_name))


def mock_dns(*args, **kwargs):
    return mock_task(*args, **kwargs)


@interface.implementer(IDNSMappingTask)
class MockAddDNSMappingTask(AbstractTask):

    NAME = 'add_dns_mapping'
    TC = mock_dns

    def __call__(self, dns_name):
        return self.task.apply_async((dns_name))



@interface.implementer(ISetupEnvironmentTask)
class SetupEnvironmentTask(object):

    def __init__(self, app):
        self.app = app

    def __call__(self, site_id, site_name, dns_name):
        ha = IHaproxyBackendTask(self.app).task
        dns = IDNSMappingTask(self.app).task
        prov = IProvisionEnvironmentTask(self.app).task

        ha = ha.s(site_id, dns_name)
        dns = dns.s(dns_name)
        prov = prov.s(site_id, site_name, dns_name)

        return group(ha, dns, prov)()


def main():
    setHooks()
    context = config.ConfigurationMachine()
    xmlconfig.registerCommonDirectives(context)

    xmlconfig.file('configure.zcml',
                   context=context,
                   package=dottedname.resolve('nti.environments.management'))
    
    from .worker import app
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=False)
    args = parser.parse_args()

    task = ISetupEnvironmentTask(app)

    result = task('foo', 'bar', 'baz.nextthought.io')

    from IPython.core.debugger import Tracer; Tracer()()

if __name__ == "__main__":
    main()
