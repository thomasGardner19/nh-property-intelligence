-- Bootstrap the project execution role and a small auto-suspending warehouse.
-- Run this script as ACCOUNTADMIN (or an equivalent account-level admin role).
-- After this script, grant NHPI_ENGINEER directly to your Snowflake user once:
--   GRANT ROLE NHPI_ENGINEER TO USER <YOUR_USER_NAME>;

USE ROLE ACCOUNTADMIN;

CREATE ROLE IF NOT EXISTS NHPI_ENGINEER;
GRANT ROLE NHPI_ENGINEER TO ROLE SYSADMIN;

CREATE WAREHOUSE IF NOT EXISTS NHPI_XS
    WAREHOUSE_SIZE = 'XSMALL'
    AUTO_SUSPEND = 60
    AUTO_RESUME = TRUE
    INITIALLY_SUSPENDED = TRUE;

GRANT USAGE, OPERATE ON WAREHOUSE NHPI_XS TO ROLE NHPI_ENGINEER;
