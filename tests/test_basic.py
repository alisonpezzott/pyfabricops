"""Basic tests for pyfabricops package."""

import logging
import os
import sys

import pytest

# Add src to path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pyfabricops as pf


def test_package_import():
    """Test that the package can be imported."""
    assert pf is not None


def test_package_has_version():
    """Test that the package has a version attribute."""
    assert hasattr(pf, '__version__')
    assert pf.__version__ is not None


def test_set_auth_provider():
    """Test that auth provider can be set."""
    # This should not raise an exception
    pf.set_auth_provider('env')


@pytest.mark.skipif(
    not all(
        [
            os.getenv('FAB_CLIENT_ID'),
            os.getenv('FAB_CLIENT_SECRET'),
            os.getenv('FAB_TENANT_ID'),
        ]
    ),
    reason='Fabric credentials not available',
)
def test_list_workspaces_with_credentials():
    """Test list_workspaces when credentials are available."""
    pf.set_auth_provider('env')
    workspaces = pf.list_workspaces()
    assert isinstance(workspaces, list)


def __basic_test():
    """Manual test function for development."""
    pf.enable_notebook_logging(level=logging.INFO)
    pf.set_auth_provider('env')
    workspaces = pf.list_workspaces(df=True)
    print(workspaces)


if __name__ == '__main__':
    __basic_test()
