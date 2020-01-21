"""
A simulated environment setup task and accompanying script
entry point.
"""

from dns.resolver import query as dnsresolver
from dns.resolver import NXDOMAIN

from zope import interface

from .interfaces import IProvisionEnvironmentTask
from .interfaces import IDNSMappingTask

from .tasks import AbstractTask
from .tasks import mock_task

def is_dns_name_available(name):
    try:
        return not bool(dnsresolver(name))
    except NXDOMAIN:
        return True

def mock_dns(*args, **kwargs):
    return mock_task(*args, **kwargs)


@interface.implementer(IDNSMappingTask)
class MockAddDNSMappingTask(AbstractTask):

    NAME = 'add_dns_mapping'
    TC = mock_dns

    def __call__(self, dns_name):
        return self.task.apply_async((dns_name))
