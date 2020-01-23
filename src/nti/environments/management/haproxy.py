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

from zope import component

from zope import interface

from zope.component.hooks import setHooks

from zope.configuration import config
from zope.configuration import xmlconfig

from zope.dottedname import resolve as dottedname


from .interfaces import IHaproxyBackendTask
from .interfaces import IHaproxyConfigurator
from .interfaces import ISettings

from .tasks import AbstractTask
from .tasks import mock_task

logger = __import__('logging').getLogger(__name__)

_BACKEND_DEFINITION = r"""backend $SITE_ID_backend
    mode http
    option http-server-close
    timeout server 15m

    option httpchk GET /_ops/ping HTTP/1.1\r\nHost:\ localhost

    server node1 $SITE_ID.nti:8086 weight 1 send-proxy
"""

_REPLACEMENT_PATTERN = "$SITE_ID"

def backend_filename(site_id):
    return f"10-{site_id}.cfg"

def write_backend(site_id, folder):
    """
    Write an haproxy backend definition for site_id to the given
    location.
    """
    filename = backend_filename(site_id)
    path = os.path.join(folder, filename)

    logger.info('Adding haproxy backend definition file=(%s) site=(%s)', path, site_id)
    with open(path, 'x') as f:
        f.write(_BACKEND_DEFINITION.replace(_REPLACEMENT_PATTERN, site_id))

def add_backend_mapping(map_location, dns_name, site_id):
    """
    DANGER: This function writes to a shared resource which we currently make
    no attempt at locking. We expect to be invoked via a serial celery queue.

    Add the dns->backend mapping to the mapping file.

    This is obviously at risk for concurrency issues especially
    with multiple processes involved. We handle that now by ensuring
    the worker processing these tasks does so serial.

    TODO add some sort of locking / lock file in case the serial processing
    gets screwed up.

    TODO Haproxy 1.8 let's us manipulate the mappings through the API
    but it's unclear if this is ever automatically flushed to disk. We
    can probably come up with something safer than this approach.

    https://www.haproxy.com/blog/introduction-to-haproxy-maps/#editing-with-the-runtime-api

    """
    logger.info('Updating haproxy backend map map=(%s) site=(%s) dns_name(%s)',
                map_location, site_id, dns_name)
    with open(map_location, 'a') as f:
        f.write(f'{dns_name} {site_id}_backend\n')

def reload_haproxy_cfg(haproxy_podname):
    """
    Reload the haproxy config by sending it a SIGUSR2. It runs
    inside a pod so we have to use podman.

    Invokes `podman kill --signal=SIGUSR2 <podname>`

    Moving to haproxy 2.0 would allow us to use the api to do this.
    """

    logger.info('Sending SIGUSR2 to pod named %s', haproxy_podname)
    completed_process = subprocess.run(['podman', 'kill', '--signal=SIGUSR2', haproxy_podname],
                                       check=True)
    logger.info('SIGUSR2 sent to pod named %s. Completed with code=(%i)',
                haproxy_podname, completed_process.return_code)
    

@interface.implementer(IHaproxyConfigurator)
class HAProxyConfigurator(object):
    """
    An object that can configure haproxy. This is setup right now
    to work with haproxy 1.8 running in a podman pod.
    """

    def __init__(self, backends_folder, backend_map, pod_name):
        self.backends_folder = backends_folder
        self.backend_map = backend_map
        self.pod_name = pod_name   
    
    def add_backend(self, site_id, dns_name):
        logger.info('Adding haproxy backend for site=(%s) dns_name=(%s)', site_id, dns_name)
        write_backend(site_id, self.backends_folder)
        add_backend_mapping(self.backend_map, dns_name, site_id)

    def reload_config(self):
        logger.info('Issuing reload of haproxy config')
        reload_haproxy_cfg(self.pod_name)

def _haproxy_configurator_factory():
    settings = component.getUtility(ISettings)
    haproxy = settings['haproxy']
    haproxy_config_root = haproxy['config_root']
    haproxy_map = os.path.join(haproxy_config_root, 'maps/env.map')
    pod_name = haproxy['pod_name']

    return HAProxyConfigurator(haproxy_config_root, haproxy_map, pod_name)

def configure_haproxy(task, site_id, dns_name):
    configurator = component.getUtility(IHaproxyConfigurator)
    configurator.add_backend(site_id, dns_name)
    configurator.reload_config()

def mock_haproxy(*args, **kwargs):
    return mock_task(*args, **kwargs)

@interface.implementer(IHaproxyBackendTask)
class SetupHAProxyBackend(AbstractTask):

    NAME = 'create_haproxy_backend'
    TC = configure_haproxy

    def __call__(self, site_id, dns_name):
        return self.task.apply_async((site_id, dns_name))


@interface.implementer(IHaproxyBackendTask)
class MockSetupHAProxyBackend(SetupHAProxyBackend):

    NAME = 'mock_' + SetupHAProxyBackend.NAME
    TC = mock_haproxy

