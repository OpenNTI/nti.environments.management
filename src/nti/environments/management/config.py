from configparser import ConfigParser

from zope import component
from zope import interface

import os

from .interfaces import ISettings

def configure_settings(config=None):
    """
    Configures and returns settings from our configuration.
    We look for our configuration location in the provided config
    and by environment variable.
    """
    if config is None:
        config = {}
        
    locations = [os.environ.get('NTI_MANAGEMENT_CONFIG', None), config.get('nti.environments.management.config', None)]
    
    config = ConfigParser()
    config.read([l for l in locations if l])

    interface.alsoProvides(ISettings)

    component.getGlobalSiteManager().registerUtility(config, ISettings)
    
    return config

def is_devmode(config):
    return os.getenv('DEVMODE', False) or config.getboolean('general', 'devmode', fallback=False)
