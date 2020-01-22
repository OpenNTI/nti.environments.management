"""
A simulated environment setup task and accompanying script
entry point.
"""

import boto3

from dns.resolver import query as dnsresolver
from dns.resolver import NXDOMAIN

from zope import component
from zope import interface

from nti.tools.aws.route53 import add_dns_recordset

from .interfaces import IDNSAliasRecordCreator
from .interfaces import IDNSMappingTask
from .interfaces import ISettings

from .tasks import AbstractTask
from .tasks import mock_task

logger = __import__('logging').getLogger(__name__)

def is_dns_name_available(name):
    try:
        return not bool(dnsresolver(name))
    except NXDOMAIN:
        return True

def mock_dns(*args, **kwargs):
    return mock_task(*args, **kwargs)


def _add_dns_mapping(task, dns_name):
    """
    Creates an alias A record for the provided dns_name.
    Zone and alias_target come from configuration
    """
    component.getUtility(IDNSAliasRecordCreator).add_alias(dns_name)

@interface.implementer(IDNSAliasRecordCreator)
class DNSAliasAdder(object):
    
    def __init__(self, client, zone, target):
        assert zone[-1] == '.', 'Zones must end in "."'
        
        self.client = client
        self.zone = zone
        self.target = target

    def add_alias(self, dns_name):
        logger.info('Creating A record alias for %s to %s in zone %s', dns_name, self.target, self.zone)
        add_dns_recordset(self.client, self.zone, dns_name, alias_target=self.target)

def _record_creator_factory():
    settings = component.getUtility(ISettings)['dns']
    client = boto3.client('route53')

    return DNSAliasAdder(client, settings['zone'], settings['alias_target'])

@interface.implementer(IDNSMappingTask)
class AddDNSMappingTask(AbstractTask):

    NAME = 'add_dns_mapping'
    TC = _add_dns_mapping

    def __call__(self, dns_name):
        return self.task.apply_async((dns_name, ))


@interface.implementer(IDNSMappingTask)
class MockAddDNSMappingTask(AddDNSMappingTask):

    NAME = 'mock_' + AddDNSMappingTask.NAME
    TC = mock_dns

