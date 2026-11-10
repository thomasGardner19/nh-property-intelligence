"""Read-only Snowflake environment preflight. No secrets are logged."""
from contextlib import closing

from nh_property_intelligence.config import Settings
from nh_property_intelligence.snowflake import connect_snowflake


def main() -> None:
    with closing(connect_snowflake(Settings())) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT CURRENT_ROLE(), CURRENT_WAREHOUSE(), CURRENT_DATABASE()")
        role, warehouse, database = cursor.fetchone()
        if (role, warehouse, database) != (
            "NHPI_ENGINEER", "NHPI_XS", "NH_PROPERTY_INTELLIGENCE"
        ):
            raise RuntimeError("Unexpected Snowflake execution context")
        print("SNOWFLAKE_PREFLIGHT_CONTEXT_OK")
        for name in ("CENSUS_ACS_MUNICIPALITY", "DRA_MUNICIPAL_TAX_RATES", "FHFA_COUNTY_HPI"):
            cursor.execute(f"SELECT COUNT(*) FROM NH_PROPERTY_INTELLIGENCE.RAW.{name}")
            print(f"RAW_{name}_ROWS={cursor.fetchone()[0]}")


if __name__ == "__main__":
    main()
