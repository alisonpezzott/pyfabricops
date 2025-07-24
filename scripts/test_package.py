#!/usr/bin/env python3
"""
Test script to verify the package installation and basic functionality.
"""


def test_import():
    """Test if the package can be imported successfully."""
    try:
        import pyfabricops

        print(
            f'✅ pyfabricops imported successfully, version: {pyfabricops.__version__}'
        )
        return True
    except ImportError as e:
        print(f'❌ Failed to import pyfabricops: {e}')
        return False


def test_basic_functions():
    """Test if basic functions are available."""
    try:
        import pyfabricops as pf

        # Test if key functions are available
        functions_to_test = [
            'set_auth_provider',
            'list_workspaces',
            'list_capacities',
            '_api_request',
        ]

        for func_name in functions_to_test:
            if hasattr(pf, func_name):
                print(f"✅ Function '{func_name}' is available")
            else:
                print(f"❌ Function '{func_name}' is missing")
                return False

        return True
    except Exception as e:
        print(f'❌ Error testing functions: {e}')
        return False


def main():
    """Main test function."""
    print('🧪 Testing pyfabricops package...')
    print('=' * 50)

    success = True

    # Test import
    success &= test_import()
    print()

    # Test basic functions
    success &= test_basic_functions()
    print()

    if success:
        print('🎉 All tests passed! Package is ready for use.')
    else:
        print('❌ Some tests failed. Please check the package.')

    return 0 if success else 1


if __name__ == '__main__':
    exit(main())
