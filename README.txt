NTI Environments Management
===========================

Getting Started
---------------

- Change directory into your newly created project.

    cd nti.environments.management

- Create a Python virtual environment.

    python3 -m venv env

- Upgrade packaging tools.

    env/bin/pip install --upgrade pip setuptools

- Install the project in editable mode with its testing requirements.

    env/bin/pip install -e ".[test]"

- Run your project's tests.

    env/bin/pytest
