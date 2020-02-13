import argparse
import os
import time
import socket
import subprocess
import json
import functools
import socket

from celery import group

from dns.resolver import query as dnsresolver
from dns.resolver import NXDOMAIN

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

    option httpchk GET /_ops/ping HTTP/1.1\r\nHost:\ $SITE_ID

    server node1 $SITE_ID.nti:8086 weight 1 on-error mark-down check inter 500 rise 2 fall 2 observe layer7 send-proxy
"""

_REPLACEMENT_PATTERN = "$SITE_ID"

_DEFAULT_ADMIN_SOCKET = "/run/haproxy-master.sock"

def send_command(socket_file, command, read_timeout=1):
    try:
        unix_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        unix_socket.settimeout(read_timeout)
        unix_socket.connect(socket_file)
        unix_socket.send(bytes(command + '\n', 'utf-8'))
        data = str(unix_socket.recv(65536), 'utf-8')
    except (socket.timeout):
        """
        TODO: Add logic to determine if the lack of response was expected.
        If it was not expected we need to rethrow the exception.
        """
        data = False
    finally:
        unix_socket.close()
    return data

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

class HAProxyCommandException(Exception):
    """
    Raised if an error occurs communicating with haproxy
    """

def check_haproxy_status_output(output):
    """
    Given output from haproxy proc status, parse to see if the config was reloaded
    succesfully. We're looking for an entry of type 'worker' with a relative pid of 1
    and reloads of 0.

    #<PID>          <type>          <relative PID>  <reloads>       <uptime>        <version>
    8               master          0               82              9d00h27m02s     2.1.1
    # workers
    1017            worker          1               0               0d00h01m28s     2.1.1
    # old workers
    657             worker          [was: 1]        17              0d05h35m30s     2.1.1
    # programs

    A failed reload looks like this:

    #<PID>          <type>          <relative PID>  <reloads>       <uptime>        <version>
    8               master          0               27              5d22h03m17s     2.1.1
    # workers
    # old workers
    177             worker          [was: 1]        14              0d20h36m10s     2.1.1
    105             worker          [was: 1]        19              0d21h32m50s     2.1.1
    # programs

    Notice no non-old workers

    """

    # The format here is aweful. were looking for something in the workers section

    in_workers=False
    workers = []
    for line in output.split('\n'):
        if line.startswith('# workers'):
            # At the start of the workers section. If we saw this already that's output
            # we didn't expect
            if in_workers:
                raise HAProxyCommandException('Unexpected "workers" section')
            in_workers = True
            continue

        if in_workers:
            # if we encounter a new section and we are in workers, that means we reached
            # the end of workers and need to exit
            if line.startswith('#'):
                break
            else:
                #Found a worker
                worker = line.split()
                if len(worker) != 6:
                    raise HAProxyCommandException('Encoutered worker line of unexpected format. %i columns not 6' % len(worker))
                workers.append(line.split())
        # Not in workers so ignore

    if len(workers) < 1:
        # No workers on the new config.
        raise HAProxyCommandException('Reload Failed. No workers on new config')

    # TODO it's unclear if we need to check reload count

    return True


def reload_haproxy_cfg(admin_socket, check_reload=True):
    """
    Reload the haproxy config by sending the reload command over
    the admin socket.
    """
    logger.info('Sending \'reload\' command to haproxy master process.')
    send_command(admin_socket, 'reload')
    logger.info('\'reload\' command sent.')

    # The damn reload command gives zero feedback in the success or failure
    # case. So now try to get the proc status and figure out if things
    # were restarted. Again, we're run serially so were are hand waving around
    # a ton of synchronization issues.

    if check_reload:
        # The afore mentioned reload command also puts the socket in a weird state
        # for a very short time afterwards as well. For now we will just sleep for
        # a short fixed amount of time and hope that works.
        time.sleep(0.2)

        logger.info('Sending \'show proc\' command to haproxy master process.')
        output = send_command(admin_socket, 'show proc')
        logger.info('\'show proc\' command sent.')

        try:
            check_haproxy_status_output(output)
        except HAProxyCommandException as e:
            logger.exception('HAProxy Reload failed')
            raise HAProxyCommandException('Haproxy reload failed: %s', e)

@interface.implementer(IHaproxyConfigurator)
class HAProxyConfigurator(object):
    """
    An object that can configure haproxy.
    """

    def __init__(self, backends_folder, backend_map, admin_socket=_DEFAULT_ADMIN_SOCKET):
        self.backends_folder = backends_folder
        self.backend_map = backend_map
        self.admin_socket = admin_socket

    def add_backend(self, site_id, dns_name):
        logger.info('Adding haproxy backend for site=(%s) dns_name=(%s)', site_id, dns_name)
        write_backend(site_id, self.backends_folder)
        add_backend_mapping(self.backend_map, dns_name, site_id)

    def reload_config(self):
        logger.info('Issuing reload of haproxy config')
        reload_haproxy_cfg(self.admin_socket, False)

def _haproxy_configurator_factory():
    settings = component.getUtility(ISettings)
    haproxy = settings['haproxy']
    haproxy_config_root = haproxy['config_root']
    haproxy_map = os.path.join(haproxy_config_root, 'maps/env.map')
    admin_socket = haproxy['admin_socket']

    return HAProxyConfigurator(haproxy_config_root, haproxy_map, admin_socket)

class InternalDNSNotReady(Exception):
    """
    Raised when the internal dns name is not ready
    """
    pass

def configure_haproxy(task, site_id, dns_name, dns_check_interval=1, dns_max_wait=30):
    """
    Generate the haproxy backend and reload the configuration. Note
    that the internal poddns name must exist for this to work. We expect
    that to have completed before we are called or shortly after.

    TODO Ideally we would make this job dependent on the job generating
    that dns entry, but that is the pod creation job. It happens right towards the
    beginning so we just wait. Sloppy, but we don't want to wait the 90 seconds
    for that job and it's not easy to extract the dns task to it's own job that happens
    before everything.
    """
    configurator = component.getUtility(IHaproxyConfigurator)
    configurator.add_backend(site_id, dns_name)
    configurator.reload_config()

def mock_haproxy(task, *args, **kwargs):
    val = mock_task(task, *args, **kwargs)
    if task.request.retries < 5:
        logger.info('Retrying mock haproxy task')
        task.retry()
    return val

@interface.implementer(IHaproxyBackendTask)
class SetupHAProxyBackend(AbstractTask):

    NAME = 'create_haproxy_backend'
    TC = configure_haproxy
    QUEUE = 'tier1'

    @classmethod
    def bind(cls, app, **kwargs):
        super(SetupHAProxyBackend, cls).bind(app, max_retries=10, default_retry_delay=2)

    def __call__(self, site_id, dns_name):
        dns_name = dns_name.lower()
        return self.task.apply_async((site_id, dns_name))


@interface.implementer(IHaproxyBackendTask)
class MockSetupHAProxyBackend(SetupHAProxyBackend):

    NAME = 'mock_' + SetupHAProxyBackend.NAME
    TC = mock_haproxy

