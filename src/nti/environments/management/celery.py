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

import random

import functools

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

def _maybe_set(settings, name, envvar, coercer=None, default=None):
    if envvar in os.environ:
        value = os.environ[envvar]
        if coercer is not None:
            value = coercer(value)
        settings[name] = value
    elif default is not None:
        settings.setdefault(name, default)

class Celery(_Celery):

    def task(self, *args, **opts):
        opts.setdefault('shared', False)
        return super(Celery, self).task(*args, **opts)

class Task(_Task):
    pass

def configure_celery(name='nti.environments.management', settings=None):
    """
    Setup a celery instance with the given name and settings.
    Settings specified in the environment are preferred to those in
    the settings object.

    The returned application is not finalized. Callers can continue to
    modify the application configuration but they must call finalize

    """
    if settings is None:
        settings = {}

    _maybe_set(settings, "celery.broker_url", "BROKER_URL")
    _maybe_set(settings, "celery.backend_url", "RESULT_URL")

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

    app = _Celery(name, autofinalize=False, set_as_current=False)

    app.conf.update(
        accept_content=["json", "msgpack"],
        broker_url=broker_url,
        broker_transport_options=broker_transport_options,
        backend_url=settings["celery.backend_url"],
        task_serializer="json",
        worker_disable_rate_limits=True
    )
    
    app.Task = Task

    return app

@connect_on_app_finalize
def register_tasks(app):
    """
    Register our tasks with the celery application.

    TODO while convenient, this probably isn't the proper place
    or time to do this.
    """
    from .envsetup import setup_site
    app.task(bind=True, name='init_env')(setup_site)
