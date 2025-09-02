import os
import sys
from dotenv import load_dotenv
import pandas as pd

# FIX: Configure environment before any .NET imports
adomdclientdll_path = r"C:\Program Files\DAX Studio\bin"
if os.path.exists(adomdclientdll_path):
    # Add to system PATH
    if adomdclientdll_path not in os.environ.get('PATH', ''):
        os.environ['PATH'] = adomdclientdll_path + ';' + os.environ.get('PATH', '')
    
    # Add to Python sys.path
    if adomdclientdll_path not in sys.path:
        sys.path.insert(0, adomdclientdll_path)

    print(f"✅ Configured path of AdomdClient.dll: {adomdclientdll_path}")

try:
    from pyadomd import Pyadomd
    print("✅ pyadomd successfully imported")
except Exception as e:
    print(f"❌ Error importing pyadomd: {e}")
    print("   Trying alternative solution...")

    # Try to load the DLL manually via clr
    try:
        import clr
        clr.AddReference(os.path.join(adomdclientdll_path, "Microsoft.AnalysisServices.AdomdClient.dll"))
        from pyadomd import Pyadomd
        print("✅ pyadomd successfully imported using manual CLR!")
    except Exception as e2:
        print(f"❌ Alternative solution also failed: {e2}")
        sys.exit(1)

load_dotenv()

app_id = os.getenv('FAB_CLIENT_ID')
client_secret = os.getenv('FAB_CLIENT_SECRET')
tenant_id = os.getenv('FAB_TENANT_ID')

workspace = 'Sandbox_Fabric'
semantic_model = 'Call_Logs'
table_name = 'Call_Logs'   # e.g., "FactSales"

# XMLA connection string for Power BI (format corrected)
conn_str = (
    f"Data Source=powerbi://api.powerbi.com/v1.0/myorg/{workspace};"
    f"Initial Catalog={semantic_model};"
    f"User ID=app:{app_id}@{tenant_id};"
    f"Password={client_secret};"
) 

DMV_QUERY = """
SELECT * FROM $SYSTEM.TMSCHEMA_PARTITIONS
"""

def fetch_partitions():
    with Pyadomd(conn_str) as conn:
        with conn.cursor().execute(DMV_QUERY) as cur:
            cols = [c[0] for c in cur.description]
            rows = cur.fetchall()
            df = pd.DataFrame(rows, columns=cols)
    return df

def fetch_tables_lookup():
    # Build a lookup to map TableID -> Table Name (from TMSCHEMA_TABLES)
    query = """
    SELECT [ID], [Name]
    FROM $SYSTEM.TMSCHEMA_TABLES
    """
    with Pyadomd(conn_str) as conn:
        with conn.cursor().execute(query) as cur:
            cols = [c[0] for c in cur.description]
            rows = cur.fetchall()
            return pd.DataFrame(rows, columns=cols)

def main():
    parts = fetch_partitions()
    if parts.empty:
        print("No partitions returned. Check permissions, XMLA endpoint, and dataset access.")
        return

    tables = fetch_tables_lookup()
    df = parts.merge(tables.rename(columns={"ID": "TableID", "Name": "TableName"}), on="TableID", how="left")

    # Optional: filter by table
    if table_name:
        df = df[df["TableName"].str.lower() == table_name.lower()].copy()

    # Sort for readability
    sort_cols = [c for c in ["TableName", "Name", "RefreshedTime"] if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols, ascending=[True, True, False])

    return df

if __name__ == "__main__":
    print(main()) 
