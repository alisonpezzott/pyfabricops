from ..api.api import api_request
from ..utils.exceptions import ResourceNotFoundError
from ..utils.logging import get_logger

logger = get_logger(__name__)


def get_user_id(email):
    """Get user ID by email"""
    response = api_request(
        endpoint=f'/users/{email}',
        audience='graph',
    )
    if response.get('id'):
        logger.success(f"User {email} found with ID: {response['id']}")
        return response['id']
    else:
        raise ResourceNotFoundError(f'User {email} not found')


def get_user_email(id):
    """Get user email by ID"""
    response = api_request(
        endpoint=f'/users/{id}',
        audience='graph',
    )
    if response.get('userPrincipalName'):
        logger.success(
            f"User {id} found with email: {response['userPrincipalName']}"
        )
        return response['userPrincipalName']
    else:
        raise ResourceNotFoundError(f'User {id} not found')


def get_security_group_id(group_name):
    """Get group ID by display name or mail"""
    response = api_request(
        endpoint=f"/groups?$filter=displayName eq '{group_name}'",
        audience='graph',
    )
    id = response['value'][0]['id']
    if id:
        logger.success(f'Group {group_name} found with ID: {id}')
        return id
    else:
        raise ResourceNotFoundError(f'Group {group_name} not found')


def get_security_group_name(group_id):
    """Get group display name by ID"""
    response = api_request(
        endpoint=f"/groups?$filter=id eq '{group_id}'",
        audience='graph',
    )
    name = response['value'][0]['displayName']
    if name:
        logger.success(f'Group {group_id} found with name: {name}')
        return name
    else:
        raise ResourceNotFoundError(f'Group {group_id} not found')


def get_app_registration_id(app_name):
    """Get application (app registration) ID by display name"""
    response = api_request(
        endpoint=f"/applications?$filter=displayName eq '{app_name}'",
        audience='graph',
    )
    id = response['value'][0]['id']
    if id:
        logger.success(f'App registration {app_name} found with ID: {id}')
        return id
    else:
        raise ResourceNotFoundError(f'App registration {app_name} not found')


def get_app_registration_name(app_id):
    """Get application (app registration) ID by display name"""
    response = api_request(
        endpoint=f"/applications?$filter=id eq '{app_id}'",
        audience='graph',
    )
    name = response['value'][0]['displayName']
    if name:
        logger.success(f'App registration {app_id} found with name: {name}')
        return name
    else:
        raise ResourceNotFoundError(f'App registration {app_id} not found')


def get_service_principal_id(spn_name):
    """Get application (app registration) ID by display name"""
    response = api_request(
        endpoint=f"/servicePrincipals?$filter=displayName eq '{spn_name}'",
        audience='graph',
    )
    id = response['value'][0]['id']
    if id:
        logger.success(f'Service Principal {spn_name} found with ID: {id}')
        return id
    else:
        raise ResourceNotFoundError(f'Service Principal {spn_name} not found')


def get_service_principal_name(spn_id):
    """Get application (app registration) ID by display name"""
    response = api_request(
        endpoint=f"/servicePrincipals?$filter=id eq '{spn_id}'",
        audience='graph',
    )
    name = response['value'][0]['displayName']
    if name:
        logger.success(f'Service Principal {spn_id} found with name: {name}')
        return name
    else:
        raise ResourceNotFoundError(f'Service Principal {spn_id} not found')
