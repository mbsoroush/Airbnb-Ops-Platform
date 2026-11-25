"""Names shared by the SQL, analytics code, dashboard definitions and (later) the DAG.

Kept free of heavy imports so it can be used without the `db` extra.
"""

SCHEMA = "analytics"
VIEW = f"{SCHEMA}.mv_airbnb_neighbourhood_summary"
