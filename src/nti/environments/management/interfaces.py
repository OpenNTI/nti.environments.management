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


class IProvisionEnvironmentTask(IApplicationTask):
    """
    The task responsible for setting up an environment.
    """

    def __call__(site_id, site_name, dns_name):
        """
        Provisions a new dedicated trial environment with the given
        site_id, site_name, and dns_name.
        """

class IHaproxyBackendTask(IApplicationTask):
    """
    Sets up the new haproxy backend and configures
    the haproxy mapping
    """

    def __call__(site_id, dns_name):
        """
        Dispatch a task that setups up the tier1 haproxy
        backend and mapping.
        """

class IDNSMappingTask(IApplicationTask):
    """
    A task capable of setting up dns entries for a site
    """

    def __call__(dns_name):
        """
        Given a dns_name, add an appropriate dns entry
        to route traffic to the tier1 haproxy.
        """


class ISetupEnvironmentTask(IApplicationTask):
    """
    A composite task that creates and configures an environment.
    """

    def __call__(site_id, site_name, dns_name):
        """
        Provisions an environment with an IProvisionEnvironmentTask,
        and establishes dns and haproxy configuration with IDNSMappingTask
        and IHaproxyBackendTask respectively. This task acts like a celery
        group and returns a celery GroupResult
        """