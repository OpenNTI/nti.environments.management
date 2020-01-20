from zope import interface

from nti.schema.field import Object

class ICeleryApp(interface.Interface):
    """
    A celery.Celery application. Tasks that are dispatched via the
    normal celery methods are dispatched immediately and in a non
    transactional manner. Special care must be taken when using this
    inside the broader pyramid/zope architecture, especially with respect
    to the transactional nature of the system. For example how does your usage
    of this react to TransactionLoop retries, the two phase commit process, etc.
    """
    pass


class IApplicationTask(interface.Interface):
    """
    An object that represents an asynchronous task. Typically
    regsitered as an adapter on an ICeleryApp
    """

    app = Object(ICeleryApp,
                 title='The celery app hosting this task',
                 required=True)

    task = interface.Attribute('The celery task for this task')

    name = interface.Attribute('The name of this task')


    def __call__(*args, **kwargs):
        """
        Immediately enqueues the asyncronous task for execution. Concrete
        implementations are expected to define args and kwargs.

        The return value should be the celery AsyncResult
        """


class ISetupEnvironmentTask(IApplicationTask):
    """
    The task responsible for setting up an environment.
    """

    def __call__(site_id, site_name, dns_name):
        """
        Provisions a new dedicated trial environment with the given
        site_id, site_name, and dns_name.
        """


    
