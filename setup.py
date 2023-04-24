import os

from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, 'README.txt')) as f:
    README = f.read()
with open(os.path.join(here, 'CHANGES.txt')) as f:
    CHANGES = f.read()

requires = [
    'redis < 3.4.0, >= 3.3.0',
    'celery[redis,sqlalchemy]',
    'zope.interface',
    'zope.component',
    'nti.schema',
    'zope.dottedname',
    'zope.configuration',
    'zope.security',
    'dnspython',
    'requests',
    'nti.tools.aws @ git+ssh://git@github.com/OpenNTI/nti.tools.aws',
    'perfmetrics'
]

tests_require = [
    'nti.testing',
    'fudge'
]

docs_require = []

setup(
    name='nti.environments.management',
    version_format='{tag}.dev{commits}+{sha}',
    setup_requires=['very-good-setuptools-git-version'],
    description='NTI Environments Management',
    long_description=README + '\n\n' + CHANGES,
    classifiers=[
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python',
        'Framework :: Pyramid',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: WWW/HTTP :: WSGI :: Application',
    ],
    author='',
    author_email='',
    url='',
    packages=find_packages('src'),
    package_dir={'': 'src'},
    namespace_packages=['nti', 'nti.environments'],
    include_package_data=True,
    zip_safe=False,
    extras_require={
        'test': tests_require,
        'docs': docs_require,
        'flower': ['flower']
    },
    package_data={
        '': ['*.ini','*.mako', '*.zcml'],
    },
    install_requires=requires,
    entry_points={
    },
    scripts=[
        'bin/mocks/nti_environments_management_mock_init'
    ]
)
