#!/usr/bin/env python3
"""
Test script to verify the package installation and basic functionality.
"""


def test_import():
    """Test if the package can be imported successfully."""
    try:
        import pyfabricops

        print(
            f"✅ pyfabricops imported successfully, version: {pyfabricops.__version__}"
        )
    except ImportError as e:
        raise AssertionError(f"❌ Failed to import pyfabricops: {e}") from e


def test_basic_functions():
    """Test if basic functions are available."""
    try:
        import pyfabricops as pf

        # Test if key functions are available
        functions_to_test = [
            "set_auth_provider",
            "list_workspaces",
            "list_capacities",
            "api_request",
        ]

        for func_name in functions_to_test:
            if hasattr(pf, func_name):
                print(f"✅ Function '{func_name}' is available")
            else:
                raise AssertionError(f"❌ Function '{func_name}' is missing")
    except Exception as e:
        raise AssertionError(f"❌ Error testing functions: {e}") from e


def main():
    """Main test function."""
    print("🧪 Testing pyfabricops package...")
    print("=" * 50)

    success = True

    # Test import
    try:
        test_import()
    except AssertionError as e:
        print(e)
        success = False
    print()

    # Test basic functions
    try:
        test_basic_functions()
    except AssertionError as e:
        print(e)
        success = False
    print()

    if success:
        print("🎉 All tests passed! Package is ready for use.")
    else:
        print("❌ Some tests failed. Please check the package.")

    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
