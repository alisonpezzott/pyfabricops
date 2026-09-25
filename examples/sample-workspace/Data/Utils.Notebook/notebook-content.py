# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {}
# META }

# MARKDOWN ********************

# # Utils
# Helpers shared by the notebooks of this workspace. A notebook loads them
# with `%run Utils`.

# CELL ********************

from pyspark.sql import DataFrame
from pyspark.sql import functions as F


def with_ingestion_time(df: DataFrame) -> DataFrame:
    """Add the technical column _ingestion_ts, the time of the load."""
    return df.withColumn("_ingestion_ts", F.current_timestamp())

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
