from hamcrest import assert_that
from hamcrest import is_

import unittest

from ..dns import is_dns_name_available

class TestDNS(unittest.TestCase):

    def test_dns_name_checking(self):

        # work.nextthought.com is a legitimate site and dns reservation as of 1/21/2020
        assert_that(is_dns_name_available('work.nextthought.com'), is_(False))
        assert_that(is_dns_name_available('work.nextthought.io'), is_(True))
