from hamcrest import is_
from hamcrest import raises
from hamcrest import calling
from hamcrest import assert_that

import fudge

from requests.exceptions import HTTPError
from requests.exceptions import ConnectionError

import unittest

from . import SharedConfiguringTestLayer

from ..tasks import SiteInfo
from ..tasks import _do_verify_site
from ..tasks import SiteVerificationTimeout
from ..tasks import SiteVerificationException


class TestTasks(unittest.TestCase):

    layer = SharedConfiguringTestLayer

    @fudge.patch('nti.environments.management.tasks._do_ping_site')
    def test_verify(self, mock_ping):
        """
        Validate we can loop and query to see if our site is eventually up
        and responding.
        """
        fake_ping = mock_ping.is_callable()
        fake_ping.returns(None)

        site_info = SiteInfo(site_id=1234, dns_name="dns.name")

        def call_verify():
            return _do_verify_site(site_info, timeout=2, tries=6, wait=1)

        # Eventually times out
        assert_that(calling(call_verify),
                    raises(SiteVerificationTimeout))

        # Or can return successfully
        fake_ping.next_call().returns(object())
        assert_that(call_verify(), is_(True))

        class MockResponse(object):
            def __init__(self, status_code):
                self.status_code = status_code

        cannot_connect_response = MockResponse(503)
        not_found_response = MockResponse(404)
        unknown_response = MockResponse(500)
        http_error1 = HTTPError(response=cannot_connect_response)
        http_error2 = HTTPError(response=not_found_response)
        # Or can fail a few times and eventually succeed
        fake_ping.next_call().returns(None)
        fake_ping.next_call().raises(ConnectionError())
        fake_ping.next_call().raises(http_error1)
        fake_ping.next_call().raises(http_error2)
        fake_ping.next_call().returns(True)
        assert_that(call_verify(), is_(True))

        # Unknown HTTPError also fails
        http_error3 = HTTPError(response=unknown_response)
        fake_ping.next_call().raises(http_error3)
        assert_that(calling(call_verify),
                    raises(SiteVerificationException))
