"""
Establishes a celery application that acts as the worker.

This module can be passed as the -A argument of the 
`celery worker` command.
"""

from .celery import configure_celery

app = configure_celery()

app.finalize()

