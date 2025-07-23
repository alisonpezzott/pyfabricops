from typing import Optional

from ._core import api_core_request, lro_handler, pagination_handler
from ._endpoint_templates import ENDPOINT_TEMPLATES
from ._exceptions import RequestError
from ._logging import get_logger

logger = get_logger(__name__)


def _list_generic(endpoint: str, workspace_id: Optional[str] = None):
    if endpoint not in ENDPOINT_TEMPLATES:
        raise RequestError(f'Unknown template name: {endpoint}')

    template = ENDPOINT_TEMPLATES[endpoint]

    if template['requires_workspace_id'] and workspace_id is None:
        raise RequestError(
            f'Workspace ID is required for endpoint: {endpoint}'
        )

    response = api_core_request(
        endpoint=template['endpoint']
        if not template['requires_workspace_id']
        else f"{template['endpoint_prefix']}{workspace_id}{template['endpoint']}",
        audience=template['audience'],
        content_type=template['content_type'],
        payload=template['payload'],
        data=template['data'],
        params=template['params'],
        method=template['method'],
        return_raw=template['return_raw'],
    )

    if template['return_raw']:
        return response

    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None

    if template['support_pagination']:
        paginated_response = pagination_handler(response)
        return paginated_response.data.get('value', [])


def _get_generic(
    endpoint: str,
    workspace_id: Optional[str] = None,
    item_id: Optional[str] = None,
):
    if endpoint not in ENDPOINT_TEMPLATES:
        raise RequestError(f'Unknown template name: {endpoint}')

    template = ENDPOINT_TEMPLATES[endpoint]

    if template['requires_workspace_id'] and workspace_id is None:
        raise RequestError(
            f'Workspace ID is required for endpoint: {endpoint}'
        )

    response = api_core_request(
        endpoint=f"{template['endpoint']}/{item_id}"
        if not template['requires_workspace_id']
        else f"{template['endpoint_prefix']}{workspace_id}{template['endpoint']}/{item_id}",
        audience=template['audience'],
        content_type=template['content_type'],
        payload=template['payload'],
        data=template['data'],
        params=template['params'],
        method=template['method'],
        return_raw=template['return_raw'],
    )

    if template['return_raw']:
        return response

    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None

    return response.data


def _delete_generic(
    endpoint: str,
    workspace_id: Optional[str] = None,
    item_id: Optional[str] = None,
):
    if endpoint not in ENDPOINT_TEMPLATES:
        raise RequestError(f'Unknown template name: {endpoint}')

    template = ENDPOINT_TEMPLATES[endpoint]

    if template['requires_workspace_id'] and workspace_id is None:
        raise RequestError(
            f'Workspace ID is required for endpoint: {endpoint}'
        )

    response = api_core_request(
        endpoint=f"{template['endpoint']}/{item_id}"
        if not template['requires_workspace_id']
        else f"{template['endpoint_prefix']}{workspace_id}{template['endpoint']}/{item_id}",
        audience=template['audience'],
        content_type=template['content_type'],
        payload=template['payload'],
        data=template['data'],
        params=template['params'],
        method='delete',
        return_raw=template['return_raw'],
    )

    if template['return_raw']:
        return response

    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None

    logger.success(f'Deleted {endpoint} with ID: {item_id}')
    return None


def _post_generic(
    endpoint: str,
    workspace_id: Optional[str] = None,
    item_id: Optional[str] = None,
    payload: Optional[dict] = None,
):
    if endpoint not in ENDPOINT_TEMPLATES:
        raise RequestError(f'Unknown template name: {endpoint}')

    template = ENDPOINT_TEMPLATES[endpoint]

    if template['requires_workspace_id'] and workspace_id is None:
        raise RequestError(
            f'Workspace ID is required for endpoint: {endpoint}'
        )

    endpoint = template['endpoint'] if not template['requires_workspace_id'] else f"{template['endpoint_prefix']}{workspace_id}{template['endpoint']}"
    
    if not item_id is None:
        endpoint += f"/{item_id}"

    if not template['endpoint_suffix'] is None:
        endpoint += template['endpoint_suffix']

    response = api_core_request(
        endpoint=endpoint,
        audience=template['audience'],
        content_type=template['content_type'],
        payload=payload or template['payload'],
        data=template['data'],
        params=template['params'],
        method='post',
        return_raw=template['return_raw'],
    )

    if template['return_raw']:
        return response

    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None

    if response.status_code == 202:
        logger.debug('Long-running operation detected, handling LRO...')
        lro_response = lro_handler(response)
        if not lro_response.success:
            logger.warning(
                f'{lro_response.status_code}: {lro_response.error}.'
            )
            return None
        elif not lro_response.data:
            logger.info(f'Long-running operation returned no data.')
            return None
        return lro_response.data

    return response.data


def _patch_generic(
    endpoint: str,
    workspace_id: Optional[str] = None,
    item_id: Optional[str] = None,
    payload: Optional[dict] = None,
):
    if endpoint not in ENDPOINT_TEMPLATES:
        raise RequestError(f'Unknown template name: {endpoint}')

    template = ENDPOINT_TEMPLATES[endpoint]

    if template['requires_workspace_id'] and workspace_id is None:
        raise RequestError(
            f'Workspace ID is required for endpoint: {endpoint}'
        )

    response = api_core_request(
        endpoint=f"{template['endpoint']}/{item_id}"
        if not template['requires_workspace_id']
        else f"{template['endpoint_prefix']}{workspace_id}{template['endpoint']}/{item_id}",
        audience=template['audience'],
        content_type=template['content_type'],
        payload=payload or template['payload'],
        data=template['data'],
        params=template['params'],
        method='patch',
        return_raw=template['return_raw'],
    )

    if template['return_raw']:
        return response

    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None

    if response.status_code == 202:
        logger.debug('Long-running operation detected, handling LRO...')
        lro_response = lro_handler(response)
        if not lro_response.success:
            logger.warning(
                f'{lro_response.status_code}: {lro_response.error}.'
            )
            return None
        return lro_response.data

    return response.data
