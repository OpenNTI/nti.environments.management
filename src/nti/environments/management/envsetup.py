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

from zope.component.hooks import setHooks

from zope.configuration import config
from zope.configuration import xmlconfig

from zope.dottedname import resolve as dottedname

from zope import interface

from .interfaces import ISetupEnvironmentTask

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

SETUP_TASK_NAME = 'init_env'

@interface.implementer(ISetupEnvironmentTask)
class SetupTask(object):

    name = SETUP_TASK_NAME

    @classmethod
    def bind(cls, app):
        app.task(bind=True, name=cls.name)(setup_site)

    def __init__(self, app):
        self.app = app

    @property
    def task(self):
        return self.app.tasks[self.name]

    def __call__(self, site_id, site_name, dns_name):
        return self.task.apply_async((site_id, site_name, dns_name))
    
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

if __name__ == "__main__":
    main()
