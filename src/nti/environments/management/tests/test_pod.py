from hamcrest import assert_that
from hamcrest import calling
from hamcrest import raises
from hamcrest import is_

import fudge

import os

import subprocess

import tempfile

import unittest

from zope import component

from . import SharedConfiguringTestLayer

from ..interfaces import IEnvironmentProvisioner

from ..pod import _pod_root_init_log
from ..pod import _provisioner_factory



class TestDNS(unittest.TestCase):

    layer = SharedConfiguringTestLayer

    def setUp(self):
        self.site_id = 'S123456'
        self.podroot = tempfile.TemporaryDirectory()

    def test_init_log_location(self):
        assert_that(_pod_root_init_log(self.site_id), is_('/tmp/pods/%s/logs/init.log'% self.site_id))
        self.podroot.cleanup()
        self.podroot = None

    @fudge.patch('subprocess.run')
    @fudge.patch('nti.environments.management.pod._pod_root_init_log')
    def test_provisioner(self, mock_run, mock_init_log):
        logfile = os.path.join(self.podroot.name, 'init.log')
        mock_init_log.expects_call().with_args(self.site_id).returns(logfile)
                                           
        prov = _provisioner_factory()

        assert_that(IEnvironmentProvisioner.providedBy(prov))

        assert_that(prov.script_name, is_('init_pod_environment'))

        site_id = self.site_id
        site_name = 'foo'
        dns_name = 'bar.nextthot.com'

        mock_run.expects_call().with_args([prov.script_name, site_id, site_name, dns_name],
                                          check=False,
                                          capture_output=True,
                                          encoding='utf-8',
                                          shell=True)
        fake_process = mock_run.returns_fake(name='subprocess.CompletedProcess').is_a_stub()
        fake_process.has_attr(stderr='foo', stdout='{"admin_invitation": "foo"}', returncode=0)

        result = prov.provision_environment(site_id, site_name, dns_name)

        assert_that(result, is_('foo'))

        log = None
        with open(logfile, 'r') as f:
            log = f.read()

        assert_that(log, is_('foo'))

    @fudge.patch('subprocess.run')
    @fudge.patch('nti.environments.management.pod._pod_root_init_log')
    def test_provisioner_error(self, mock_run, mock_init_log):
        logfile = os.path.join(self.podroot.name, 'init.log')
        mock_init_log.expects_call().with_args(self.site_id).returns(logfile)
                                           
        prov = _provisioner_factory()

        assert_that(IEnvironmentProvisioner.providedBy(prov))

        assert_that(prov.script_name, is_('init_pod_environment'))

        site_id = self.site_id
        site_name = 'foo'
        dns_name = 'bar.nextthot.com'

        # Now if instead we return a non 0 exit code, we get a log still but also an exception is raised
        mock_run.expects_call().with_args([prov.script_name, site_id, site_name, dns_name],
                                          check=False,
                                          capture_output=True,
                                          encoding='utf-8',
                                          shell=True)
        fake_process = mock_run.returns_fake(name='subprocess.CompletedProcess').is_a_stub()
        fake_process.has_attr(stderr='an error occurred', stdout='', returncode=127)
        fake_process.provides('check_returncode').raises(subprocess.CalledProcessError(127, 'foo'))

        assert_that(calling(prov.provision_environment).with_args(site_id, site_name, dns_name),
                    raises(subprocess.CalledProcessError))

        log = None
        with open(logfile, 'r') as f:
            log = f.read()

        assert_that(log, is_('an error occurred'))
        
        

        
        
        
        

        
