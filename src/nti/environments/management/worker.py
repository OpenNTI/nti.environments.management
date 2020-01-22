"""
Establishes a celery application that acts as the worker.

This module can be passed as the -A argument of the 
`celery worker` command.
"""

from configparser import ConfigParser

import os

from .celery import configure_celery
from .config import configure_settings
from .config import is_devmode

from .interfaces import ISettings

from zope import component
from zope import interface

from zope.component.hooks import setHooks

from zope.configuration import config as zconfig
from zope.configuration import xmlconfig

from zope.dottedname import resolve as dottedname

# TODO the worker loads a module for it's setup
# So we load the zcml we want here. How can we make sure this
# only happens in the context of spinning up the worker?
# Doing it at import time is really nasty....

setHooks()

# Load and register our settings first
config = configure_settings()

context = zconfig.ConfigurationMachine()

if is_devmode(config):
    context.provideFeature('devmode')

xmlconfig.registerCommonDirectives(context)

xmlconfig.file('configure.zcml',
               context=context,
               package=dottedname.resolve('nti.environments.management'))

app = configure_celery(settings=config['celery'])

app.finalize()

