#!/usr/bin/env python
# -*- coding: utf-8 -*-

# disable: accessing protected members, too many methods
# pylint: disable=W0212,R0904

import os

from zope import component

import zope.testing.cleanup

from nti.testing.layers import GCLayerMixin
from nti.testing.layers import ZopeComponentLayer
from nti.testing.layers import ConfiguringLayerMixin

from ..config import configure_settings

from ..interfaces import ISettings


class SharedConfiguringTestLayer(ZopeComponentLayer,
                                 GCLayerMixin,
                                 ConfiguringLayerMixin):

    set_up_packages = ('nti.environments.management', )

    @classmethod
    def setUp(cls):
        config = {'nti.environments.management.config': os.path.join(os.path.dirname(__file__), 'test.ini')}
        configure_settings(config)
        cls.__envconfig = configure_settings(config)
        cls.setUpPackages()

    @classmethod
    def tearDown(cls):
        cls.tearDownPackages()
        if cls.__envconfig:
            component.getGlobalSiteManager().unregisterUtility(cls.__envconfig, ISettings)
            del cls.__envconfig
            
        zope.testing.cleanup.cleanUp()

    @classmethod
    def testSetUp(cls, test=None):
        pass

    @classmethod
    def testTearDown(cls):
        pass
