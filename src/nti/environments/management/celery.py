# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Copied from https://github.com/pypa/warehouse/blob/1fbb4ac752e68b5840b9e09b68e44a165569bfa6/warehouse/tasks.py

import os

import urllib.parse as urlparse

import celery

import celery
import celery.app.backends
import celery.backends.redis

from celery import Celery as _Celery
from celery import Task as _Task
from celery._state import connect_on_app_finalize

from kombu import binding
from kombu import Exchange
from kombu import Queue

import functools

import random

from zope.component.hooks import setHooks

from zope.configuration import config
from zope.configuration import xmlconfig

from zope.dottedname import resolve as dottedname

from zope.component import getGlobalSiteManager

from zope import interface

from .interfaces import ICeleryApp
from .interfaces import IApplicationTask

logger = __import__('logging').getLogger(__name__)

# We need to trick Celery into supporting rediss:// URLs which is how redis-py
# signals that you should use Redis with TLS.
celery.app.backends.BACKEND_ALIASES[
    "rediss"
] = "nti.environments.management.celery:TLSRedisBackend"  # noqa


# We need to register that the sqs:// url scheme uses a netloc
urlparse.uses_netloc.append("sqs")

class TLSRedisBackend(celery.backends.redis.RedisBackend):
    """
    A version of the redis backend supporting TLS
    """
    def _params_from_url(self, url, defaults):
        params = super()._params_from_url(url, defaults)
        params.update({"connection_class": self.redis.SSLConnection})
        return params

@interface.implementer(ICeleryApp)    
class Celery(_Celery):

    def task(self, *args, **opts):
        opts.setdefault('shared', False)
        return super(Celery, self).task(*args, **opts)


class Task(_Task):
    pass

def setup_routing(app):
    """
    We route tasks to queues based on type. Many of our tasks have to run
    on specific hosts. For example the task to setup a pod enivironment has to
    run on the host machine. The tasks that currently maninuplate tier1 haproxy
    rely on updating configs (currently) and therefore have to run on the tier1 box.

    TODO we're oddly coupled to our individual tasks here, which is a shame. This
    feels janky, but it works, and we're still learning...
    """

    # Require explicit queue creation
    app.conf.task_create_missing_queues = False
    app.conf.task_default_queue = 'default'

    # First setup our default queues and exchanges. This is where tasks route
    # to by default.

    # We send everything through one exchange right now
    default_exchange = Exchange('default', type='direct')

    default_queue = Queue('default', default_exchange, routing_key='default')

    # Now setup some queues

    # First is a queue for tasks that can run on any available host system. For example
    # Things such as spinning up a new environment
    any_hosts_queue = Queue('any_host', default_exchange, routing_key='any_host')

    # A queue for things that need to run on, or interact with, the tier one proxy.
    # For example manipulating haproxy backends
    tier1_queue = Queue('tier1', default_exchange, routing_key='tier1')

    # A queue for route53 dns requests
    dns_queue = Queue('dns', default_exchange, routing_key='dns')

    app.conf.task_queues = (any_hosts_queue, tier1_queue, dns_queue, default_queue, )

    # Now we need to route tasks. In general routing happens based on the
    # routing information given to the task at call time, the routing information
    # on the Task subclass, then the router configuration.
    #
    # It's documented best practice to control routing in the configuration. we do that
    # here.

    # This is where things get icky because we have different task names depending
    # on how zcml is loaded. Wither either do something like prefix/suffix on the name
    # or each task has to tell us how to route. In general I get the impression it shouldn't
    # be the tasks decision, but our tasks are coupled with where they need to run in general
    # so we take the easy approach for now.
    routes = {}

    for taskcls in _bindable_tasks():
        if taskcls.QUEUE is None:
            continue

        routes[taskcls.NAME] = {
            'queue': taskcls.QUEUE,
            'routing_key': taskcls.QUEUE
        }

    logger.info('Configuring routes %s', routes)

    app.conf.task_routes = routes
    

def configure_celery(name='nti.environments.management', settings=None, loader=None):
    """
    Setup a celery instance with the given name and settings.
    Settings specified in the environment are preferred to those in
    the settings object.

    The returned application is not finalized. Callers can continue to
    modify the application configuration but they must call finalize

    """
    if settings is None:
        settings = {}

    if 'celery' in settings:
        settings = settings['celery']
        

    broker_transport_options = {}

    broker_url = settings["celery.broker_url"]
    if broker_url.startswith("sqs://"):
        parsed_url = urlparse.urlparse(broker_url)
        parsed_query = urlparse.parse_qs(parsed_url.query)
        # Celery doesn't handle paths/query arms being passed into the SQS broker,
        # so we'll jsut remove them from here.
        broker_url = urlparse.urlunparse(parsed_url[:2] + ("", "", "", ""))

        if "queue_name_prefix" in parsed_query:
            broker_transport_options["queue_name_prefix"] = (
                parsed_query["queue_name_prefix"][0] + "-"
            )

        if "region" in parsed_query:
            broker_transport_options["region"] = parsed_query["region"][0]

    app = Celery(name, autofinalize=False, set_as_current=False)

    app.conf.update(
        accept_content=["json", "msgpack", "pickle"],
        broker_url=broker_url,
        broker_transport_options=broker_transport_options,
        result_backend=settings["celery.backend_url"],
        task_serializer="pickle",
        results_serializer="pickle",
        worker_disable_rate_limits=True
    )
    
    app.Task = Task

    setup_routing(app)
    
    return app

def _bindable_tasks(registry=None):
    """
    Look for any adapter registration that implements IApplicationTask
    This is probably really slow, but it allows us to not have to switch the
    mocks in and out here, we rely on the zcml implementations
    """
    if registry is None:
        registry = getGlobalSiteManager()

    for adapter in registry.registeredAdapters():
        if adapter.provided.isOrExtends(IApplicationTask) \
           and getattr(adapter.factory, 'bind', None):
            yield adapter.factory

@connect_on_app_finalize
def register_tasks(app):
    """
    Register our tasks with the celery application.

    TODO while convenient, this probably isn't the proper place
    or time to do this.
    """

    for taskcls in _bindable_tasks():
        taskcls.bind(app)
    
