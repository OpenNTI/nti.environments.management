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


class IAsyncResult(interface.Interface):
    """
    Represents an asynchronous celery result. e.g.
    celery.result.AsyncResult or similar.
    """

    id = interface.Attribute('The task identifier')

    def ready():
        """
        Return :const:`True` if the task has executed.

        If the task is still running, pending, or is waiting
        for retry then :const:`False` is returned.
        """


    def get(*args, **kwargs):
        """
        Get the results of the task. See
        https://docs.celeryproject.org/en/stable/_modules/celery/result.html#AsyncResult.get

        NOTE this call blocks by default if the task is not ready
        """

    def successful():
        """
        Return :const:`True` if the task executed successfully.
        """


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

    def restore_task(task_info):
        """
        Restores an async result for the given task_info.
        This is an implementation of ITaskResult. Subclasses may return
        a more specific interface.
        """

    def save_task(async_result):
        """
        Save the async_result for retrieval by the returned task_info
        latter. This ensures restore_task can return a proper value.

        """

class IEnvironmentProvisioner(interface.Interface):
    """
    An object that can provision a container environment installation.
    Right now this is registered as a utility, but these could in theory
    be registered based off of some specification file if we had
    different levels of things we needed to initialize.
    """

    def provision_environment(site_id, site_name, dns_name, customer_name, customer_email):
        """
        Setup a new environment for the provided site_id, with the given
        name and dns_name. We expect this is invoked on the machine that
        will host the containers
        """

class IProvisionEnvironmentTask(IApplicationTask):
    """
    The task responsible for setting up an environment.
    """

    def __call__(site_id, site_name, dns_name, name, email):
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

class IHaproxyReloadTask(IApplicationTask):
    """
    A task that simply reloads haproxy
    """

    def __call__():
        """
        Dispatch a task that simply reloads the tier1 haproxy.
        """


class IHaproxyConfigurator(interface.Interface):
    """
    An object capable of configuring haproxy
    """

    def add_backend(site_id, dns_name):
        """
        Configures an haproxy backend for the given site_id
        and sets up an appropriate backend mapping
        """

    def reload_config():
        """
        Gracefully reloads the haproxy configuration
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

class IDNSAliasRecordCreator(interface.Interface):
    """
    An object that can create dns A record aliases.
    """

    def add_alias(self, dns_name):
        """
        Add an alias for the following dns name
        """


class IInitializedSiteInfo(interface.Interface):

    dns_name = interface.Attribute('The dns_name configured')

    site_id = interface.Attribute('The site_id setup')

    host = interface.Attribute('The identity of the host system')

    admin_invitation = interface.Attribute('The invitation that can be used to create an initial admin account')

    ds_site_id = interface.Attribute('The dataserver site id/name that was created')

class ISetupEnvironmentTask(IApplicationTask):
    """
    A composite task that creates and configures an environment.
    """

    def __call__(site_id, site_name, dns_name, name, email):
        """
        Provisions an environment with an IProvisionEnvironmentTask,
        and establishes dns and haproxy configuration with IDNSMappingTask
        and IHaproxyBackendTask respectively. This task acts like a celery
        group and returns a ISetupEnvironmentResult
        """

class ISettings(interface.Interface):
    """
    A dictionary like object providing configuration
    """
