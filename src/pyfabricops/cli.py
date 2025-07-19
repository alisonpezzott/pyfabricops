import argparse
import json
from . import (
    __version__,
    list_workspaces,
    get_workspace,
    list_capacities,
    get_capacity,
    set_auth_provider,
    list_connections,
    list_data_pipelines,
    list_items,
)


def create_workspace_commands(subparsers):
    """Create workspace-related command parsers."""
    subparsers.add_parser('list-workspaces', help='List available workspaces')
    
    get_ws_parser = subparsers.add_parser('get-workspace', help='Get workspace details')
    get_ws_parser.add_argument('workspace', help='Workspace name or ID')


def create_capacity_commands(subparsers):
    """Create capacity-related command parsers."""
    subparsers.add_parser('list-capacities', help='List available capacities')
    
    get_cap_parser = subparsers.add_parser('get-capacity', help='Get capacity details')
    get_cap_parser.add_argument('capacity', help='Capacity name or ID')


def create_connection_commands(subparsers):
    """Create connection-related command parsers."""
    subparsers.add_parser('list-connections', help='List available connections')


def create_workspace_item_commands(subparsers):
    """Create workspace item command parsers."""
    list_dp_parser = subparsers.add_parser('list-data-pipelines', help='List data pipelines in a workspace')
    list_dp_parser.add_argument('workspace', help='Workspace name or ID')

    list_items_parser = subparsers.add_parser('list-items', help='List items in a workspace')
    list_items_parser.add_argument('workspace', help='Workspace name or ID')


def setup_parser():
    """Set up the argument parser with all commands."""
    parser = argparse.ArgumentParser(
        prog='pyfabricops', 
        description='CLI for pyfabricops - Microsoft Fabric operations'
    )
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')

    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Create command groups
    create_workspace_commands(subparsers)
    create_capacity_commands(subparsers)
    create_connection_commands(subparsers)
    create_workspace_item_commands(subparsers)
    
    return parser


def execute_command(args):
    """Execute the appropriate command based on args."""
    # Configure authentication from environment variables
    set_auth_provider('env')

    if args.command == 'list-workspaces':
        return list_workspaces()
    elif args.command == 'get-workspace':
        return get_workspace(args.workspace)
    elif args.command == 'list-capacities':
        return list_capacities()
    elif args.command == 'get-capacity':
        return get_capacity(args.capacity)
    elif args.command == 'list-connections':
        return list_connections()
    elif args.command == 'list-data-pipelines':
        return list_data_pipelines(args.workspace)
    elif args.command == 'list-items':
        return list_items(args.workspace)
    else:
        return None


def main(argv=None):
    """Entry point for the pyfabricops command line interface."""
    parser = setup_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    result = execute_command(args)
    
    if result is not None:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
