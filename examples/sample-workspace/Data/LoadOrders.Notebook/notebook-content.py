# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "11111111-1111-4111-8111-111111111111",
# META       "default_lakehouse_name": "Bronze",
# META       "default_lakehouse_workspace_id": "00000000-0000-0000-0000-000000000000"
# META     }
# META   }
# META }

# MARKDOWN ********************

# # Load orders
# Writes the sample orders to the `orders` Delta table of the default
# lakehouse, Bronze. The DailyLoad pipeline runs this notebook.

# CELL ********************

from datetime import date
from decimal import Decimal

from pyspark.sql.types import (
    DateType,
    DecimalType,
    StringType,
    StructField,
    StructType,
)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

%run Utils

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

ORDERS_SCHEMA = StructType(
    [
        StructField("order_id", StringType(), nullable=False),
        StructField("order_date", DateType(), nullable=False),
        StructField("product", StringType(), nullable=False),
        StructField("amount", DecimalType(18, 2), nullable=False),
    ]
)

orders = spark.createDataFrame(
    [
        ("SO-1001", date(2026, 1, 5), "Bikes", Decimal("1250.50")),
        ("SO-1002", date(2026, 1, 6), "Helmets", Decimal("320.00")),
        ("SO-1003", date(2026, 1, 6), "Gloves", Decimal("145.75")),
    ],
    ORDERS_SCHEMA,
)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# The sample is small and fixed, so each run reloads it whole.
(
    with_ingestion_time(orders)
    .write.format("delta")
    .mode("overwrite")
    .saveAsTable("orders")
)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
