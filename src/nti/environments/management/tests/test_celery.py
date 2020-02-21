from hamcrest import assert_that
from hamcrest import is_
from hamcrest import contains_inanyorder

from perfmetrics.testing.matchers import is_counter
from perfmetrics.testing.matchers import is_timer

from perfmetrics.testing import FakeStatsDClient

from perfmetrics import set_statsd_client

import uuid
import unittest

from ..celery import task_prerun_handler
from ..celery import task_postrun_handler
from ..celery import task_success_handler
from ..celery import task_failure_handler

class MockTask(object):

    name = None
    id = None

    def __init__(self, name):
        self.name = name
        self.id = uuid.uuid4().hex

class TestCeleryStats(unittest.TestCase):

    statsd = None

    def setUp(self):
        self.statsd = FakeStatsDClient()
        set_statsd_client(self.statsd)

    def tearDown(self):
        self.statsd = None
        set_statsd_client(None)

    def _simulate_task(self, name, success=True):
        task = MockTask(name)
        task_prerun_handler(task.id, task)
        task_postrun_handler(task.id, task)
        if success:
            task_success_handler(task)
        else:
            task_failure_handler(task)
        return task

    def test_successful_task(self):
        """
        We expect a prerun, postrun, and success counter along
        with a task tiemr.
        """
        task = self._simulate_task('mytask')

        assert_that(self.statsd, contains_inanyorder(is_counter('celery.task.mytask.prerun'),
                                                     is_counter('celery.task.mytask.postrun'),
                                                     is_counter('celery.task.mytask.success'),
                                                     is_timer('celery.task.mytask.t')))

    def test_failure_task(self):
        """
        We expect a prerun, postrun, and failure counter along
        with a task tiemr.
        """
        task = self._simulate_task('mytask', success=False)

        assert_that(self.statsd, contains_inanyorder(is_counter('celery.task.mytask.prerun'),
                                                     is_counter('celery.task.mytask.postrun'),
                                                     is_counter('celery.task.mytask.failure'),
                                                     is_timer('celery.task.mytask.t')))
        
