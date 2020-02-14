from hamcrest import assert_that
from hamcrest import calling
from hamcrest import has_length
from hamcrest import is_
from hamcrest import raises

import fudge

import unittest

import os

import tempfile

from zope import component

from . import SharedConfiguringTestLayer

from ..haproxy import add_backend_mapping
from ..haproxy import backend_filename
from ..haproxy import check_haproxy_status_output
from ..haproxy import write_backend
from ..haproxy import HAProxyCommandException
from ..haproxy import reload_haproxy_cfg

from ..interfaces import IHaproxyConfigurator



_EXPECTED_BACKED = r"""backend S123456789ABCDEF_backend
    mode http
    option http-server-close
    timeout server 15m

    option httpchk GET /_ops/ping HTTP/1.1\r\nHost:\ localhost

    server node1 S123456789ABCDEF.nti:8086 weight 1 send-proxy
"""

GOOD_RELOAD_OUTPUT = """#<PID>          <type>          <relative PID>  <reloads>       <uptime>        <version>
8               master          0               82              9d00h27m02s     2.1.1
# workers
1017            worker          1               0               0d00h01m28s     2.1.1
# old workers
657             worker          [was: 1]        17              0d05h35m30s     2.1.1
# programs

"""

BAD_RELOAD_OUTPUT = """#<PID>          <type>          <relative PID>  <reloads>       <uptime>        <version>
8               master          0               82              9d00h27m02s     2.1.1
# workers
# old workers
657             worker          [was: 1]        17              0d05h35m30s     2.1.1
# programs

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

        assert_that(configurator.admin_socket, is_('/run/haproxy-master.sock'))
        assert_that(configurator.backend_map, is_('/tmp/haproxy/etc/maps/env.map'))
        assert_that(configurator.backends_folder, is_('/tmp/haproxy/etc/'))

        mock_reload.expects_call().with_args(configurator.admin_socket)

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

    def test_show_proc_check(self):
        assert_that(check_haproxy_status_output(GOOD_RELOAD_OUTPUT), is_(True))
        assert_that(calling(check_haproxy_status_output).with_args(BAD_RELOAD_OUTPUT),
                    raises(HAProxyCommandException))

    @fudge.patch('nti.environments.management.haproxy.send_command')
    def test_badreload_raises_in_task(self, mock_send_command):
        socket = ''

        mock_send_command.is_callable().with_args(socket, 'reload')
        mock_send_command.next_call().with_args(socket, 'show proc').returns(BAD_RELOAD_OUTPUT)

        assert_that(calling(reload_haproxy_cfg).with_args(socket), raises(HAProxyCommandException))
        
        

        
        
        
        
