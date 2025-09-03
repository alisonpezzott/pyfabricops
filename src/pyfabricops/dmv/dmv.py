import os
import sys
from pathlib import Path

import pandas as pd

from ..utils.logging import get_logger

logger = get_logger(__name__)

# Global variable to hold Pyadomd class after import
Pyadomd = None


def _set_adomd_client_dll_path(path: Path) -> bool:
    """Configure the path for AdomdClient.dll"""
    if not path.exists():
        logger.error(f'Path does not exist: {path}')
        return False

    # Add to system PATH
    if str(path) not in os.environ.get('PATH', ''):
        os.environ['PATH'] = str(path) + ';' + os.environ.get('PATH', '')

    # Add to Python sys.path
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

    logger.info(f'Configured path of AdomdClient.dll: {path}')
    return True


def import_pyadomd(
    path: Path = Path(r'C:\Program Files\DAX Studio\bin'),
) -> bool:
    """Import pyadomd with proper error handling and fallback"""
    global Pyadomd  # Make Pyadomd available globally

    # First configure the AdomdClient.dll path
    if not _set_adomd_client_dll_path(path):
        logger.error('Failed to configure AdomdClient.dll path')
        return False

    try:
        from pyadomd import Pyadomd

        logger.info('pyadomd successfully imported')
        return True
    except Exception as e:
        logger.error(f'Error importing pyadomd: {e}')
        logger.info('   Trying alternative solution...')

        # Try to load the DLL manually via clr
        try:
            import clr

            dll_path = os.path.join(
                str(path), 'Microsoft.AnalysisServices.AdomdClient.dll'
            )
            clr.AddReference(dll_path)
            from pyadomd import Pyadomd

            logger.info('pyadomd successfully imported using manual CLR!')
            return True
        except Exception as e2:
            logger.error(f'Alternative solution also failed: {e2}')
            return False


def set_dmv_connection_string_spn(
    client_id: str,
    client_secret: str,
    tenant_id: str,
    workspace_name: str,
    semantic_model_name: str,
) -> str:
    conn_str = (
        f'Data Source=powerbi://api.powerbi.com/v1.0/myorg/{workspace_name};'
        f'Initial Catalog={semantic_model_name};'
        f'User ID=app:{client_id}@{tenant_id};'
        f'Password={client_secret};'
    )
    return conn_str


def set_dmv_connection_string_user(
    user_email: str,
    password: str,
    workspace_name: str,
    semantic_model_name: str,
) -> str:
    conn_str = (
        f'Data Source=powerbi://api.powerbi.com/v1.0/myorg/{workspace_name};'
        f'Initial Catalog={semantic_model_name};'
        f'User ID={user_email};'
        f'Password={password};'
    )
    return conn_str


def evaluate_dmv_queries(
    conn_str: str,
    query: str,
) -> pd.DataFrame:
    """Execute DMV query against Power BI XMLA endpoint"""
    if Pyadomd is None:
        raise RuntimeError(
            'Pyadomd is not available. Call import_pyadomd() first.'
        )

    try:
        with Pyadomd(conn_str) as conn:
            with conn.cursor().execute(query) as cur:
                cols = [c[0] for c in cur.description]
                rows = cur.fetchall()
                df = pd.DataFrame(rows, columns=cols)
                return df
    except Exception as e:
        logger.error(f'Error executing DMV query: {e}')
        raise


def dmv_fetch_tables_raw(
    conn_str: str,
) -> pd.DataFrame:
    """
    Build a lookup to map TableID -> Table Name (from TMSCHEMA_TABLES)
    """
    query = """
    SELECT * FROM $SYSTEM.TMSCHEMA_TABLES
    """
    return evaluate_dmv_queries(conn_str, query)


def dmv_fetch_partitions_raw(
    conn_str: str,
) -> pd.DataFrame:
    """
    Build a lookup to map TableID -> Table Name (from TMSCHEMA_PARTITIONS)
    """
    query = """
    SELECT * FROM $SYSTEM.TMSCHEMA_PARTITIONS
    """
    return evaluate_dmv_queries(conn_str, query)


def dmv_fetch_partitions_enriched(
    conn_str: str,
) -> pd.DataFrame:
    """
    Enrich partition information with additional metadata.
    """
    parts = dmv_fetch_partitions_raw(conn_str)
    if parts.empty:
        print(
            'No partitions returned. Check permissions, XMLA endpoint, and semantic model access.'
        )
        return None

    tables = dmv_fetch_tables_raw(conn_str)
    tables = tables[['ID', 'Name']]
    df = parts.merge(
        tables.rename(columns={'ID': 'TableID', 'Name': 'TableName'}),
        on='TableID',
        how='left',
    )

    # Sort for readability
    sort_cols = [
        c
        for c in ['TableName', 'Name', 'RefreshedTime', 'ModifiedTime']
        if c in df.columns
    ]
    if sort_cols:
        df = df.sort_values(sort_cols, ascending=[True, True, False, False])
        df = df[['TableName', 'Name', 'RefreshedTime', 'ModifiedTime']]

    return df
