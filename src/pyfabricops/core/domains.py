from typing import Any, Dict, List, Literal, Optional, Union

from pandas import DataFrame

from ..api.api import api_request
from ..utils.decorators import df
from ..utils.logging import get_logger
from ..utils.utils import is_valid_uuid

logger = get_logger(__name__)


@df
def list_domains(
    *,
    non_empty_only: Optional[bool] = False,
    df: Optional[bool] = True,
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    List domains

    Args:
        non_empty_only (Optional[bool]): If True, only returns domains that are not empty.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, Any]], None]): A list of domains in the workspace.

    Examples:
        ```python
        list_domains() # List all domains
        list_domains(non_empty_only=True) # List only non-empty domains
        ```
    """
    resp = api_request(
        '/admin/domains',
        params={
            'nonEmptyOnly': str(non_empty_only).lower(),
            'preview': 'false',
        },
        support_pagination=True,
        return_raw=True,
    )
    return resp.json().get('domains', [])


def get_domain_id(domain_name: str) -> Union[str, None]:
    """
    Retrieves the ID of a domain by its name.

    Args:
        domain_name (str): The name of the domain.

    Returns:
        str | None: The ID of the domain if found, otherwise None.
    """
    domains = list_domains(df=False)
    for _domain in domains:
        if _domain['displayName'] == domain_name:
            return _domain['id']
    logger.warning(f"domain '{domain_name}' not found.")
    return None


def resolve_domain(domain: str) -> Union[str, None]:
    """
    Resolves a domain name to its ID.

    Args:
        domain (str): The name or ID of the domain.

    Returns:
        str | None: The ID of the domain if found, otherwise None.
    """
    if is_valid_uuid(domain):
        return domain
    else:
        return get_domain_id(domain)


@df
def get_domain(
    domain: str, *, df: Optional[bool] = True
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Get a domain in a workspace.

    Args:
        domain (str): The name or id of the domain to get.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The domain details if found, otherwise None.

    Examples:
        ```python
        get_domain(
            domain='98f6b7c8-1234-5678-90ab-cdef12345678'
        )
        ```
    """
    return api_request(
        '/admin/domains/' + resolve_domain(domain) + '?preview=false',
    )


@df
def create_domain(
    display_name: str,
    *,
    description: str = None,
    parent_domain: str = None,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Create a new domain in the tenant.

    Args:
        display_name (str): The name of the domain to create.
        description (str): The description of the domain to create.
        parent_domain (str): The name or ID of the parent domain.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The created domain details if successful, otherwise None.

    Examples:
        ```python
        create_domain(
            display_name='Newdomain',
            parent_domain_id='456e7890-e12b-34d5-a678-90abcdef1234'
        )
        ```
    """
    payload = {'displayName': display_name}

    if description:
        payload['description'] = description

    if parent_domain:
        payload['parentdomainId'] = resolve_domain(parent_domain)

    return api_request(
        '/admin/domains',
        payload=payload,
        method='post',
    )


def delete_domain(domain: str) -> None:
    """
    Delete a domain

    Args:
        domain (str): The name or ID of the domain to delete.

    Returns:
        None.

    Examples:
        ```python
        delete_domain('98f6b7c8-1234-5678-90ab-cdef12345678')
        ```
    """
    return api_request(
        '/admin/domains/' + resolve_domain(domain),
        method='delete',
    )


@df
def update_domain(
    domain: str,
    *,
    display_name: str = None,
    description: str = None,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Update a existing domain.

    Args:
        domain (str): The name or id of the current domain.
        display_name (str): The new name of the domain to update.
        description (str): The new description of the domain to update.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The updated domain details if successful, otherwise None.

    Examples:
        ```python
        update_domain(
            domain_id='98f6b7c8-1234-5678-90ab-cdef12345678',
            display_name='NewdomainName',
        )
        ```
    """
    payload = {}

    if display_name:
        payload = {'displayName': display_name}
    if description:
        payload['description'] = description

    return api_request(
        '/admin/domains/' + resolve_domain(domain),
        payload=payload,
        method='patch',
    )


@df
def list_domain_workspaces(
    domain: str,
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Returns a list of the workspaces assigned to the specified domain.

    Args:
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, Any]], None]): A list of domains in the workspace.

    Examples:
        ```python
        list_domain_workspaces('Financial')
        ```
    """
    resp = api_request(
        '/admin/domains/' + resolve_domain(domain) + '/workspaces',
        support_pagination=True,
    )
    return resp


@df
def list_domain_workspaces(
    domain: str,
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Returns a list of the workspaces assigned to the specified domain.

    Args:
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, Any]], None]): A list of domains in the workspace.

    Examples:
        ```python
        list_domain_workspaces('Financial')
        ```
    """
    resp = api_request(
        '/admin/domains/' + resolve_domain(domain) + '/workspaces',
        support_pagination=True,
    )
    return resp


@df
def list_domain_role_assignments(
    domain: str,
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Returns a list of the role assignments assigned to the specified domain.

    Args:
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, Any]], None]): A list of role assignments of the domain.

    Examples:
        ```python
        list_domain_role_assignments('Financial')
        ```
    """
    resp = api_request(
        '/admin/domains/' + resolve_domain(domain) + '/roleAssignments',
        support_pagination=True,
    )
    return resp


@df
def domain_role_assignments_bulk_assign(
    domain: str,
    payload: Dict[str, Any],
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Assign the specified admins or contributors to the domain.

    Args:
        domain (str): The name or ID of the domain.
        admins (List[str]): A list of user IDs to assign as admins.
        contributors (List[str]): A list of user IDs to assign as contributors.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, Any]], None]): A list of role assignments of the domain.

    Fabric Rest API Reference:
        https://learn.microsoft.com/en-us/rest/api/fabric/admin/domains/role-assignments-bulk-assign

    Examples:
        ```python

        domain_role_assignments_bulk_assign(
            'Financial',
            {
                "type": "Admins",
                "principals": [
                    {
                    "id": "796ce6ad-9163-4c16-9559-c68192a251de",
                    "type": "User"
                    }
                ]
            }
        )

        domain_role_assignments_bulk_assign(
            'Financial',
            {
                "type": "Contributors",
                "principals": [
                    {
                        "id": "796ce6ad-9163-4c16-9559-c68192a251de",
                        "type": "User"
                    }
                ]
            }
        )
        ```
    """
    resp = api_request(
        '/admin/domains/'
        + resolve_domain(domain)
        + '/roleAssignments/bulkAssign',
        method='post',
        payload=payload,
    )
    return resp


@df
def domain_role_assignments_bulk_unassign(
    domain: str,
    payload: Dict[str, Any],
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Assign the specified admins or contributors to the domain.

    Args:
        domain (str): The name or ID of the domain.
        admins (List[str]): A list of user IDs to assign as admins.
        contributors (List[str]): A list of user IDs to assign as contributors.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, Any]], None]): A list of role assignments of the domain.

    Fabric Rest API Reference:
        https://learn.microsoft.com/en-us/rest/api/fabric/admin/domains/role-assignments-bulk-unassign

    Examples:
        ```python

        domain_role_assignments_bulk_assign(
            'Financial',
            {
                "type": "Admins",
                "principals": [
                    {
                    "id": "796ce6ad-9163-4c16-9559-c68192a251de",
                    "type": "User"
                    }
                ]
            }
        )

        domain_role_assignments_bulk_assign(
            'Financial',
            {
                "type": "Contributors",
                "principals": [
                    {
                        "id": "796ce6ad-9163-4c16-9559-c68192a251de",
                        "type": "User"
                    }
                ]
            }
        )
        ```
    """
    resp = api_request(
        '/admin/domains/'
        + resolve_domain(domain)
        + '/roleAssignments/bulkUnassign',
        method='post',
        payload=payload,
    )
    return resp


@df
def domain_sync_role_assignments_to_subdomain(
    domain: str,
    role: Literal['Admin', 'Contributor'] = 'Admin',
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Sync the role assignments from the specified domain to its subdomains.

    Args:
        domain (str): The name or ID of the domain.
        role (Literal['Admin', 'Contributor']): The role to sync ('Admin' or 'Contributor').
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, Any]], None]): The result of the sync operation.

    Fabric Rest API Reference:
        https://learn.microsoft.com/en-us/rest/api/fabric/admin/domains/sync-role-assignments-to-subdomains

    Examples:
        ```python
        domain_sync_role_assignments_to_subdomain('Financial', role='Admin')
        ```
    """
    payload = {'role': role}
    resp = api_request(
        '/admin/domains/'
        + resolve_domain(domain)
        + '/roleAssignments/syncToSubdomains',
        method='post',
        payload=payload,
    )
    return resp


def unassign_all_domain_workspaces(domain: str) -> None:
    """
    Unassign all workspaces from the specified domain.

    Args:
        domain (str): The name or ID of the domain to unassign all workspaces.

    Returns:
        None.

    Fabric Rest API Reference:
        https://learn.microsoft.com/en-us/rest/api/fabric/admin/domains/unassign-all-domain-workspaces

    Examples:
        ```python
        unassign_all_domain_workspaces('98f6b7c8-1234-5678-90ab-cdef12345678')

        ```
    """
    return api_request(
        '/admin/domains/' + resolve_domain(domain) + '/unassignAllWorkspaces',
        method='post',
    )


def assign_domain_workspaces_by_ids(
    domain: str, workspaces: List[str]
) -> None:
    """
    Assign workspaces from the specified domain by workspace ID.

    Args:
        domain (str): The name or ID of the domain to unassign all workspaces.
        workspaces (List[str]): A list of workspace IDs to unassign from the domain.

    Returns:
        None.

    Fabric Rest API Reference:
        https://learn.microsoft.com/en-us/rest/api/fabric/admin/domains/assign-domain-workspaces-by-ids

    Examples:
        ```python
        assign_domain_workspaces_by_ids(
            '98f6b7c8-1234-5678-90ab-cdef12345678',
            [
                "e8de1852-7382-480a-8404-d5b1f5e1ab65",
                "5348d3a9-c096-4074-9083-09e3ca69c8e5",
                "ac561643-c5c5-4cf1-868e-8755a90e6fa3"
            ]
        )

        ```
    """
    payload = {'workspaceIds': workspaces}
    return api_request(
        '/admin/domains/' + resolve_domain(domain) + '/assignWorkspaces',
        method='post',
        payload=payload,
    )


def unassign_domain_workspaces_by_ids(
    domain: str, workspaces: List[str]
) -> None:
    """
    Unassign workspaces from the specified domain by workspace ID.

    Args:
        domain (str): The name or ID of the domain to unassign all workspaces.
        workspaces (List[str]): A list of workspace IDs to unassign from the domain.

    Returns:
        None.

    Fabric Rest API Reference:
        https://learn.microsoft.com/en-us/rest/api/fabric/admin/domains/unassign-domain-workspaces-by-ids

    Examples:
        ```python
        unassign_domain_workspaces_by_ids(
            '98f6b7c8-1234-5678-90ab-cdef12345678',
            [
                "e8de1852-7382-480a-8404-d5b1f5e1ab65",
                "5348d3a9-c096-4074-9083-09e3ca69c8e5",
                "ac561643-c5c5-4cf1-868e-8755a90e6fa3"
            ]
        )

        ```
    """
    payload = {'workspaceIds': workspaces}
    return api_request(
        '/admin/domains/' + resolve_domain(domain) + '/unassignWorkspaces',
        method='post',
        payload=payload,
    )


def assign_domain_workspaces_by_capacities(
    domain: str, capacities: List[str]
) -> None:
    """
    Assign all workspaces that reside on the specified capacities to the specified domain.
    Preexisting domain assignments will be overridden unless bulk reassignment is blocked by domain management tenant settings.

    Args:
        domain (str): The name or ID of the domain to assign all workspaces.
        capacities (List[str]): A list of capacities IDs to assign.

    Returns:
        None.

    Fabric Rest API Reference:
        https://learn.microsoft.com/en-us/rest/api/fabric/admin/domains/assign-domain-workspaces-by-capacities

    Examples:
        ```python
        assign_domain_workspaces_by_capacities(
            '98f6b7c8-1234-5678-90ab-cdef12345678',
            [
                "e8de1852-7382-480a-8404-d5b1f5e1ab65",
                "5348d3a9-c096-4074-9083-09e3ca69c8e5",
                "ac561643-c5c5-4cf1-868e-8755a90e6fa3"
            ]
        )

        ```
    """
    payload = {'capacitiesIds': capacities}
    return api_request(
        '/admin/domains/'
        + resolve_domain(domain)
        + '/assignWorkspacesByCapacities',
        method='post',
        payload=payload,
        support_lro=True,
    )


def assign_domain_workspaces_by_principals(
    domain: str, principals: List[Dict[str, Any]]
) -> None:
    """
    Assign workspaces to the specified domain, when one of the specified principals has admin permission in the workspace.
    Preexisting domain assignments will be overridden unless bulk reassignment is blocked by domain management tenant settings.

    Args:
        domain (str): The name or ID of the domain to assign all workspaces.
        principals (List[str]): The principals that are admins of the workspaces.

    Returns:
        None.

    Fabric Rest API Reference:
        https://learn.microsoft.com/en-us/rest/api/fabric/admin/domains/assign-domain-workspaces-by-principals

    Examples:
        ```python
        assign_domain_workspaces_by_principals(
            '98f6b7c8-1234-5678-90ab-cdef12345678',
            [
                { "id": "e8de1852-7382-480a-8404-d5b1f5e1ab65", "type": "User" },
                { "id": "5348d3a9-c096-4074-9083-09e3ca69c8e5", "type": "ServicePrincipal" }
            ]
        )

        ```
    """
    payload = {'principals': principals}
    return api_request(
        '/admin/domains/'
        + resolve_domain(domain)
        + '/assignWorkspacesByPrincipals',
        method='post',
        payload=payload,
        support_lro=True,
    )
