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

import requests

from requests.exceptions import ConnectionError
from requests.exceptions import HTTPError

from urllib.parse import urlunparse

from celery import group

from celery.result import AsyncResult
from celery.result import GroupResult
from celery.result import result_from_tuple

from zope.component.hooks import setHooks

from zope.configuration import config
from zope.configuration import xmlconfig

from zope.dottedname import resolve as dottedname

from zope import interface

from .interfaces import IInitializedSiteInfo
from .interfaces import IProvisionEnvironmentTask
from .interfaces import IDNSMappingTask
from .interfaces import IHaproxyBackendTask
from .interfaces import IHaproxyReloadTask
from .interfaces import ISetupEnvironmentTask

logger = __import__('logging').getLogger(__name__)

class SimpleTaskState(object):

    task_id = None
    version = None

    def __init__(self, id, version=1):
        self.task_id = id
        self.version = version

class AbstractTask(object):

    NAME = None
    TC = None
    QUEUE = None

    @classmethod
    def bind(cls, app, **kwargs):
        app.task(bind=True, name=cls.NAME, **kwargs)(cls.TC)

    def __init__(self, app):
        self.app = app

    @property
    def task(self):
        return self.app.tasks[self.NAME]

    def restore_task(self, state):
        """
        Restores the given task from the app we are associated with.
        """
        return result_from_tuple(state, app=self.app)


    def save_task(self, async_result):
        """
        Save the async_result for retrieval latter.
        """
        return async_result.as_tuple()


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

class SiteVerificationException(Exception):
    """
    Raised when a verification error is encountered for a setup site.
    """
    pass

class SiteVerificationTimeout(SiteVerificationException):
    """
    Raised when we cannont verify the site is setup before a timeout
    """
    pass


def _do_ping_site(url, site_id, timeout=1):
    resp = requests.get(url, timeout=timeout)

    resp.raise_for_status()

    pong = resp.json()

    pinged_site = pong.get('Site', None)
    if pinged_site != site_id.lower():
        raise SiteVerificationException('Site verification error. Expected site %s but found %s' % (site_id, pinged_site))

    return pong


def _ping_url(site_info):
    return 'https://%s/dataserver2/logon.ping' % site_info.dns_name


def _do_verify_site(site_info, timeout=2, tries=10, wait=2):
    """
    Verify the created site is accessible.
    """
    attempts = 0
    verified = False
    last_exception = None
    site_id = site_info.site_id
    url = _ping_url(site_info)
    while attempts < tries:
        try:
            pong = _do_ping_site(url, site_id, timeout=timeout)
            if pong:
                verified = True
                break
        except ConnectionError as e:
            # A retriable error, we couldn't connect to the site.
            # Possibly dns hasn't propogated
            last_exception = e
            logger.debug('ConnectionError when verifying site. %s', e)
        except HTTPError as e:
            # Some HTTPErrors we want to catch and retry on
            # for example a 503, that's likely indicative of a backend
            # that isn't up.
            # TODO the environment spin up is waiting on this currently
            # so if we still are getting this here we may not want to retry.
            last_exception = e
            code = e.response.status_code

            logger.debug('HTTPError when verifying site. %s', e)
            if code == 503 or code == 404:
                pass
            else:
                logger.exception('An error occurred when verifying site')
                raise SiteVerificationException('Unable to verify site. %s' % e)

        attempts += 1
        time.sleep(wait)

    if not verified:
        if last_exception is not None:
            raise SiteVerificationException('Unable to verify site. %s' % last_exception)
        raise SiteVerificationTimeout()

    return True


def join_setup_environment_task(task, group_result, site_info, verify_site=True):
    """
    Given a group result for a site setup, complete the site_info object
    and return it. This tasks acts as a chord callback for the group
    """

    app = task._get_app()
    ha = IHaproxyReloadTask(app)
    logger.info('Spawning haproxy reload job')
    res = ha()
    # By default celery doesn't want us running tasks synchronously from other
    # tasks http://docs.celeryq.org/en/latest/userguide/tasks.html#task-synchronous-subtasks.
    # Rightfully so as we could very very easily deadlock ourselves.
    rval = res.get(timeout=20, disable_sync_subtasks=False, propagate=False)
    logger.info('Haproxy job completed with %s', rval)

    

    # Currently the only task in our group that has output we care about is
    # the provision task. It's the last child in the group.
    # TODO how can we reduce the coupling to the group structure.
    pod_result = group_result[-1]
    host, invite = pod_result
    logger.info('Site %s spinup complete.', site_info.site_id)
    site_info.admin_invitation = invite
    site_info.host = host

    if verify_site:
        logger.info('Performing site verification for site %s', site_info.site_id)
        try:
            valid = _do_verify_site(site_info)
            if valid:
                logger.info('Site verification for site %s completed successfully',
                            site_info.site_id)
        except SiteVerificationException:
            logger.exception('Site verification failed')
            raise
    else:
        logger.warn('Bypassing site verification. Devmode?')

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

        ha = ha.s(site_id, dns_name).set(countdown=10)
        
        dns = dns.s(dns_name)
        prov = prov.s(site_id, site_name, dns_name, name, email)

        info = SiteInfo(site_id, dns_name)

        g1 = group(dns, ha, prov)

        c = ( g1 | self.join_task.s(info))
        return c()

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
