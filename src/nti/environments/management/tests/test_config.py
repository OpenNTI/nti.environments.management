from hamcrest import assert_that
from hamcrest import is_


import unittest

from zope import component

from . import SharedConfiguringTestLayer

from ..interfaces import ISettings

class TestConfig(unittest.TestCase):

    layer = SharedConfiguringTestLayer

    def test_settings_registered(self):
        settings = component.getUtility(ISettings)

        assert_that(settings['dns']['zone'], is_('nextthot.com.'))

        
