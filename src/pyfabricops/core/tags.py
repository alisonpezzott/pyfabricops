from typing import Any, Dict, List, Literal, Optional, Union

from pandas import DataFrame

from ..api.api import api_request
from ..utils.decorators import df
from ..utils.logging import get_logger
from ..utils.utils import is_valid_uuid

logger = get_logger(__name__)


@df
def list_tags(
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Returns a list of all the tenant's tags.

    Args:
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, Any]], None]): A list of tags in the workspace.

    Refs:
        https://learn.microsoft.com/en-us/rest/api/fabric/admin/tags/list-tags

    Examples:
        ```python
        list_tags()
        ```
    """
    resp = api_request(
        '/admin/tags',
        support_pagination=True,
    )
    return resp


def get_tag_id(tag_name: str) -> Union[str, None]:
    """
    Retrieves the ID of a tag by its name.

    Args:
        tag_name (str): The name of the tag.

    Returns:
        str | None: The ID of the tag if found, otherwise None.
    """
    tags = list_tags(df=False)
    for _tag in tags:
        if _tag['displayName'] == tag_name:
            return _tag['id']
    logger.warning(f"Tag '{tag_name}' not found.")
    return None


def resolve_tag(tag: str) -> Union[str, None]:
    """
    Resolves a tag name to its ID.

    Args:
        tag (str): The name or ID of the tag.

    Returns:
        str | None: The ID of the tag if found, otherwise None.
    """
    if is_valid_uuid(tag):
        return tag
    else:
        return get_tag_id(tag)


@df
def bulk_create_tags(
    payload: Dict[str, Any],
    *,
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

    Refs:
        https://learn.microsoft.com/en-us/rest/api/fabric/admin/tags/bulk-create-tags

    Examples:
        ```python

        # Create tags "Tag1" and "Tag2" under the "Tenant" scope
        bulk_create_tags(
            {
                "scope": {
                    "type": "Tenant"
                },
                "tags": [
                    {
                        "displayName": "Tag1"
                    },
                    {
                        "displayName": "Tag2"
                    }
                ]
            }
        )

        # Create tags "Tag1" and "Tag2" under the "Domain" scope
        bulk_create_tags(
            {
                "scope": {
                    "type": "Domain",
                    "domainId": "98f6b7c8-1234-5678-90ab-cdef12345678"
                },
                "tags": [
                    {
                        "displayName": "Tag1"
                    },
                    {
                        "displayName": "Tag2"
                    }
                ]
            }
        )
        ```
    """
    return api_request(
        '/admin/tags/bulkCreateTags',
        payload=payload,
        method='post',
    )


def delete_tag(tag: str) -> None:
    """
    Delete a tag by its name or ID.

    Args:
        tag (str): The name or ID of the tag to delete.

    Returns:
        None.

    Examples:
        ```python
        delete_tag('98f6b7c8-1234-5678-90ab-cdef12345678')
        ```

    Refs:
        https://learn.microsoft.com/en-us/rest/api/fabric/admin/tags/delete-tag
    """
    return api_request(
        '/admin/domains/' + resolve_tag(tag),
        method='delete',
    )


@df
def update_tag(
    tag: str,
    display_name: str = None,
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Updates the specified tag.

    Args:
        tag (str): The name or id of the current tag.
        display_name (str): The new name of the tag to update.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The updated tag details if successful, otherwise None.

    Examples:
        ```python
        update_tag(
            '98f6b7c8-1234-5678-90ab-cdef12345678',
            display_name='New Tag Name',
        )
        ```
    """
    payload = {'displayName': display_name}

    return api_request(
        '/admin/domains/' + resolve_tag(tag),
        payload=payload,
        method='patch',
    )
