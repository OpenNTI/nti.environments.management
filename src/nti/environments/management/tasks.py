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

from celery.result import AsyncResult
from celery.result import GroupResult

from zope.component.hooks import setHooks

from zope.configuration import config
from zope.configuration import xmlconfig

from zope.dottedname import resolve as dottedname

from zope import interface

from .interfaces import IInitializedSiteInfo
from .interfaces import IProvisionEnvironmentTask
from .interfaces import IDNSMappingTask
from .interfaces import IHaproxyBackendTask
from .interfaces import ISetupEnvironmentTask

logger = __import__('logging').getLogger(__name__)

class SimpleTaskState(object):

    task_id = None

    def __init__(self, id):
        self.task_id = id

class AbstractTask(object):

    NAME = None
    TC = None
    QUEUE = None

    @classmethod
    def bind(cls, app):
        app.task(bind=True, name=cls.NAME)(cls.TC)

    def __init__(self, app):
        self.app = app

    @property
    def task(self):
        return self.app.tasks[self.NAME]

    def restore_task(self, state):
        """
        Restores the given task from the app we are associated with.
        By default we restore as an AsyncResult but subclasses may override that.
        """
        task_id = state.task_id
        return AsyncResult(task_id, app=app)
        

    def save_task(async_result):
        """
        Save the async_result for retrieval latter. By default
        tasks return AsyncResults which persist automatically when
        a backend is provided. This noops, but subclasses may return
        tasks that must explicitly save. For example a celery.result.ResultSet
        """
        return SimpleTaskState(async_result.id)

    

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

    def __call__(self, site_id, site_name, dns_name, name, email):
        return self.task.apply_async((site_id, site_name, dns_name, name, email))


def mock_task(task, *args, sleep=3, result=None, **kwargs):
    time.sleep(sleep)
    return result

def join_setup_environment_task(task, group_result, site_info):
    """
    Given a group result for a site setup, complete the site_info object
    and return it. This tasks acts as a chord callback for the group
    """

    # Currently the only task in our group that has output we care about is
    # the provision task. It's the last child in the group.
    # TODO how can we reduce the coupling to the group structure.
    pod_result = group_result[-1]
    host, invite = pod_result
    logger.info('Site %s spinup complete.', site_info.site_id)
    site_info.admin_invitation = invite
    site_info.host = host
    return site_info

@interface.implementer(IInitializedSiteInfo)
class SiteInfo(object):

    dns_name = None
    site_id = None
    host = None
    admin_invitation = None

    def __init__(self, site_id, dns_name):
        self.site_id = site_id
        self.dns_name = dns_name

class SetupTaskState(SimpleTaskState):
    """
    In addition to the basic task information,
    also track the parent group state
    """

    group_id = None

    def __init__(self, task_id, group_id):
        self.task_id = task_id
        self.group_id = group_id

@interface.implementer(ISetupEnvironmentTask)
class SetupEnvironmentTask(AbstractTask):

    def __init__(self, app):
        self.app = app

    @classmethod
    def bind(cls, app):
        app.task(bind=True, name=join_setup_environment_task.__name__)(join_setup_environment_task)

    @property
    def join_task(self):
        return self.app.tasks[join_setup_environment_task.__name__]

    def __call__(self, site_id, site_name, dns_name, name, email):
        dns_name = dns_name.lower()
        
        ha = IHaproxyBackendTask(self.app).task
        dns = IDNSMappingTask(self.app).task
        prov = IProvisionEnvironmentTask(self.app).task

        ha = ha.s(site_id, dns_name)
        dns = dns.s(dns_name)
        prov = prov.s(site_id, site_name, dns_name, name, email)

        info = SiteInfo(site_id, dns_name)

        c = (group(ha, dns, prov) | self.join_task.s(info))
        return c()

    def restore_task(self, state):
        """
        Restores the given task from the app we are associated with.
        By default we restore as an AsyncResult but subclasses may override that.
        """
        task_id = state.task_id
        group_id = state.group_id

        parent = GroupResult.restore(group_id, app=self.app)
        return AsyncResult(task_id, parent=parent, app=self.app)
        

    def save_task(self, async_result):
        """
        Save the async_result for retrieval latter. By default
        tasks return AsyncResults which persist automatically when
        a backend is provided. This noops, but subclasses may return
        tasks that must explicitly save. For example a celery.result.ResultSet
        """
        async_result.parent.save()
        return SetupTaskState(async_result.id, async_result.parent.id)

def main():    
    from .worker import app
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=False)
    args = parser.parse_args()

    task = ISetupEnvironmentTask(app)

    result = task('foo', 'bar', 'baz.nextthought.io')

    print(result.get())

if __name__ == "__main__":
    main()
