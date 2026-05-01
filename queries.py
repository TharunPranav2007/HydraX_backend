# KPI Query
KPI_QUERY = """
SELECT 
    AVG(dtwl) AS avg_dtwl,
    MAX(date) AS latest_date
FROM groundwater_data
WHERE (%s IS NULL OR state_ut = %s)
"""

# Trend Query
TREND_QUERY = """
SELECT 
    EXTRACT(YEAR FROM date) AS year,
    AVG(dtwl) AS avg_dtwl
FROM groundwater_data
WHERE (%s IS NULL OR state_ut = %s)
GROUP BY year
ORDER BY year
"""

# Map Query
MAP_QUERY = """
SELECT DISTINCT ON (state_ut, district, block, village)
    state_ut, district, block, village,
    latitude, longitude, dtwl, date
FROM groundwater_data
ORDER BY state_ut, district, block, village, date DESC
"""

# Location Query
STATE_QUERY = "SELECT DISTINCT state_ut FROM groundwater_data ORDER BY state_ut"
DISTRICT_QUERY = "SELECT DISTINCT district FROM groundwater_data WHERE state_ut=%s"
BLOCK_QUERY = "SELECT DISTINCT block FROM groundwater_data WHERE district=%s"
VILLAGE_QUERY = "SELECT DISTINCT village FROM groundwater_data WHERE block=%s"

# Seasonal Query
SEASON_QUERY = """
SELECT season, AVG(dtwl) AS avg_dtwl
FROM groundwater_data
GROUP BY season
"""
