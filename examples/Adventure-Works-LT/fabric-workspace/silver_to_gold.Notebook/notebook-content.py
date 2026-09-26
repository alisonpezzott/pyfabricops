# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "00000000-0000-4000-8000-000000000202",
# META       "default_lakehouse_name": "gold",
# META       "default_lakehouse_workspace_id": "00000000-0000-4000-8000-000000000001",
# META       "known_lakehouses": [
# META         {
# META           "id": "00000000-0000-4000-8000-000000000205"
# META         },
# META         {
# META           "id": "00000000-0000-4000-8000-000000000202"
# META         }
# META       ]
# META     }
# META   }
# META }

# MARKDOWN ********************

# ## Imports

# CELL ********************

spark.conf.set('spark.sql.caseSensitive', True)

from pyspark.sql import functions as F

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Creating Schema

# CELL ********************

# MAGIC %%sql  
# MAGIC CREATE SCHEMA IF NOT EXISTS SalesLT

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Customer

# CELL ********************

df_customer = spark.sql("""
    SELECT 
        c.CustomerID,
        concat_ws(" ", c.FirstName, c.MiddleName, c.LastName) AS Customer,
        a.City,
        a.StateProvince,
        a.CountryRegion
    FROM silver.SalesLT.Customer c
    LEFT JOIN silver.SalesLT.CustomerAddress ca ON ca.CustomerID = c.CustomerID
    LEFT JOIN silver.SalesLT.Address a ON a.AddressID = ca.AddressID
""")

df_customer.write \
    .mode("overwrite") \
    .option("overwriteSchema", "true") \
    .saveAsTable("SalesLT.Customer")  


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Product  

# CELL ********************

df_product = spark.sql("""
    SELECT 
        p.ProductID,
        p.`Name` AS Product,
        p.Color,
        p.Size,
        c.`Name` AS Category,
        pm.`Name` AS Model
    FROM silver.SalesLT.Product p
    LEFT JOIN silver.SalesLT.ProductCategory c ON c.ProductCategoryID = p.ProductCategoryID
    LEFT JOIN silver.SalesLT.ProductModel pm ON pm.ProductModelID = p.ProductModelID
""")

df_product.write \
    .mode("overwrite") \
    .option("overwriteSchema", "true") \
    .saveAsTable("SalesLT.Product")  

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Sales

# CELL ********************

df_sales = spark.sql("""
    SELECT d.SalesOrderID,
        h.CustomerID,
        h.OrderDate,
        h.DueDate,
        d.ProductID,
        d.OrderQty,
        d.UnitPrice,
        d.UnitPriceDiscount
    FROM silver.SalesLT.SalesOrderDetail d
    LEFT JOIN silver.SalesLT.SalesOrderHeader h ON h.SalesOrderID = d.SalesOrderID
""")

df_sales.write \
    .mode("overwrite") \
    .option("overwriteSchema", "true") \
    .saveAsTable("SalesLT.Sales")  

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Date

# CELL ********************

# MAGIC %%sql
# MAGIC 
# MAGIC CREATE OR REPLACE TABLE SalesLT.Date
# MAGIC USING DELTA
# MAGIC AS
# MAGIC 
# MAGIC WITH calendar AS (
# MAGIC     SELECT EXPLODE(
# MAGIC         SEQUENCE(
# MAGIC             DATE('2020-01-01'),
# MAGIC             DATE('2030-12-31'),
# MAGIC             INTERVAL 1 DAY
# MAGIC         )
# MAGIC     ) AS date
# MAGIC )
# MAGIC 
# MAGIC SELECT
# MAGIC     date AS Date,
# MAGIC 
# MAGIC     YEAR(date) AS Year,
# MAGIC     QUARTER(date) AS Quarter,
# MAGIC     MONTH(date) AS Month,
# MAGIC     DATE_FORMAT(date, 'MMMM') AS MonthName,
# MAGIC     DATE_FORMAT(date, 'MMM') AS MonthShortName,
# MAGIC 
# MAGIC     CONCAT(
# MAGIC         YEAR(date),
# MAGIC         '-Q',
# MAGIC         QUARTER(date)
# MAGIC     ) AS YearQuarter,
# MAGIC 
# MAGIC     DATE_FORMAT(date, 'yyyy-MM') AS YearMonth
# MAGIC 
# MAGIC FROM calendar;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }
