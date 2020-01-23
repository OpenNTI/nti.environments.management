from hamcrest import assert_that
from hamcrest import has_length
from hamcrest import is_

import fudge

import unittest

import os

import tempfile

from zope import component

from . import SharedConfiguringTestLayer

from ..haproxy import add_backend_mapping
from ..haproxy import backend_filename
from ..haproxy import write_backend

from ..interfaces import IHaproxyConfigurator



_EXPECTED_BACKED = r"""backend S123456789ABCDEF_backend
    mode http
    option http-server-close
    timeout server 15m

    option httpchk GET /_ops/ping HTTP/1.1\r\nHost:\ localhost

    server node1 S123456789ABCDEF.nti:8086 weight 1 send-proxy
"""

class TestHaproxy(unittest.TestCase):

    folder = None

    layer = SharedConfiguringTestLayer

    def setUp(self):
        self.podid = 'S123456789ABCDEF'
        self.tempdir = tempfile.TemporaryDirectory()
        self.folder = self.tempdir.name
        os.mkdir(os.path.join(self.folder, 'maps'))
        self.mapping = os.path.join(self.folder, 'maps/env.map')
        with open(self.mapping, 'w+') as f:
            f.write('existing row\n')

    def tearDown(self):
        self.tempdir.cleanup()
        self.tempdir = None
        self.folder = None
        self.mapping = None

    def test_backend_name(self):
        assert_that(backend_filename(self.podid), is_('10-S123456789ABCDEF.cfg'))

    def test_write_backend(self):
        write_backend(self.podid, self.folder)

        with open(os.path.join(self.folder, '10-S123456789ABCDEF.cfg'), 'r') as f:
            contents = f.read()

        assert_that(contents, is_(_EXPECTED_BACKED))

    def test_add_mapping(self):
        with open(self.mapping, 'r') as f:
            assert_that(f.readlines(), has_length(1))

        add_backend_mapping(self.mapping, 'foo.nextthot.com', self.podid)

        with open(self.mapping, 'r') as f:
            lines = f.readlines()
            assert_that(lines, has_length(2))
            assert_that(lines[-1], is_('foo.nextthot.com S123456789ABCDEF_backend\n'))

    @fudge.patch('nti.environments.management.haproxy.reload_haproxy_cfg')
    def test_configurator(self, mock_reload):        
        configurator = component.getUtility(IHaproxyConfigurator)

        assert_that(configurator.pod_name, is_('tier1haproxy'))
        assert_that(configurator.backend_map, is_('/tmp/haproxy/etc/maps/env.map'))
        assert_that(configurator.backends_folder, is_('/tmp/haproxy/etc/'))

        mock_reload.expects_call().with_args(configurator.pod_name)

        configurator.backends_folder = self.folder
        configurator.backend_map = self.mapping

        configurator.add_backend(self.podid, 'foo.nextthot.com')
        configurator.reload_config()

        with open(self.mapping, 'r') as f:
            lines = f.readlines()
            assert_that(lines, has_length(2))
            assert_that(lines[-1], is_('foo.nextthot.com S123456789ABCDEF_backend\n'))

        with open(os.path.join(self.folder, '10-S123456789ABCDEF.cfg'), 'r') as f:
            contents = f.read()

        assert_that(contents, is_(_EXPECTED_BACKED))

        
        
        
        
