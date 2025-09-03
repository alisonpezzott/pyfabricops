import os
import sys
from dotenv import load_dotenv
import pandas as pd
from pathlib import Path
from ..utils.logging import get_logger

logger = get_logger(__name__)


def set_adomd_client_dll_path(path: Path):
    if path.exists():
        # Add to system PATH
        if str(path) not in os.environ.get('PATH', ''):
            os.environ['PATH'] = str(path) + ';' + os.environ.get('PATH', '')

        # Add to Python sys.path
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))

        logger.info(f"Configured path of AdomdClient.dll: {path}")
    return None

def import_pyadomd(path: Path):
    try:
        from pyadomd import Pyadomd
        logger.info("pyadomd successfully imported")
    except Exception as e:
        logger.error(f"Error importing pyadomd: {e}")
        logger.info("   Trying alternative solution...")

        # Try to load the DLL manually via clr
        try:
            import clr
            clr.AddReference(os.path.join(set_adomd_client_dll_path(path), "Microsoft.AnalysisServices.AdomdClient.dll"))
            from pyadomd import Pyadomd
            logger.info("pyadomd successfully imported using manual CLR!")
        except Exception as e2:
            logger.error(f"Alternative solution also failed: {e2}")
            sys.exit(1)
    return None


def set_dmv_connection_string_spn(
    client_id: str, 
    client_secret: str, 
    tenant_id: str, 
    workspace_name: str, 
    semantic_model_name: str
) -> str:
    conn_str = (
        f"Data Source=powerbi://api.powerbi.com/v1.0/myorg/{workspace_name};"
        f"Initial Catalog={semantic_model_name};"
        f"User ID=app:{client_id}@{tenant_id};"
        f"Password={client_secret};"
    ) 
    return conn_str


def set_dmv_connection_string_user(
    user_email: str, 
    password: str,  
    workspace_name: str, 
    semantic_model_name: str
) -> str:
    conn_str = (
        f"Data Source=powerbi://api.powerbi.com/v1.0/myorg/{workspace_name};"
        f"Initial Catalog={semantic_model_name};"
        f"User ID={user_email};"
        f"Password={password};"
    ) 
    return conn_str


def evaluate_dmv_queries(
    conn_str: str, 
    query: str
) -> pd.DataFrame:
    with Pyadomd(conn_str) as conn:
        with conn.cursor().execute(query) as cur:
            cols = [c[0] for c in cur.description]
            rows = cur.fetchall()
            return pd.DataFrame(rows, columns=cols)
        