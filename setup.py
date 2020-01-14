import os

from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, 'README.txt')) as f:
    README = f.read()
with open(os.path.join(here, 'CHANGES.txt')) as f:
    CHANGES = f.read()

requires = []

tests_require = []

docs_require = []

setup(
    name='nti.environments.management',
    version='0.0',
    description='NTI Environments Management',
    long_description=README + '\n\n' + CHANGES,
    classifiers=[
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
        'docs': docs_require
    },
    install_requires=requires,
    entry_points={
    }
)
