from hamcrest import assert_that
from hamcrest import is_

import fudge

from fudge.inspector import arg

import unittest

from zope import component

from . import SharedConfiguringTestLayer

from ..interfaces import IDNSAliasRecordCreator

from ..dns import is_dns_name_available

class TestDNS(unittest.TestCase):

    layer = SharedConfiguringTestLayer

    def test_dns_name_checking(self):

        # work.nextthought.com is a legitimate site and dns reservation as of 1/21/2020
        assert_that(is_dns_name_available('work.nextthought.com'), is_(False))
        assert_that(is_dns_name_available('work.nextthought.io'), is_(True))

    @fudge.patch('nti.environments.management.dns.add_dns_recordset')
    def test_add_mapping(self, mock_add):
        mock_add.expects_call().with_args(arg.any(),
                                          'nextthot.com.',
                                          'foo.nextthot.com',
                                          alias_target='spin.nextthot.com')
        adder = component.getUtility(IDNSAliasRecordCreator)
        adder.add_alias('foo.nextthot.com')
