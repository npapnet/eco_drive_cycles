# How to handle data (probably stale)

This document should NOT be used by AI agents. It is a work in progress and is subject to change.

# Proposed architecture (Ideal state)

- `OBDFile` is used to hold the raw data. It generates a new `Trip` object with a specific preprocessing, and converts csv and xlsx Toruqe files into the parquet which is universally optimized for data analysis.
- `Trip` is used to hold the curated data. This generates the metrics which are stored in DB. 
- `TripCollection` is used to hold a collection of `Trip` objects. This is where comparison's should be made. The question is how it is created (e.g. selecting specific entries from duckdb based on time, user, car, etc.)
  - Consider to export metrics for trip in various forms (xlsx, csv apart from duckdb)
- `DBRetriever`: A class that will be used to retrieve data from the DB. It should be used to create `TripCollection` objects.

## Points to consider

- creating a `TripCollection` object should only point to the parquet files relative to the data. As the code stands, reloading the data won't make any sense since the metrics are already computed and stored in DB.

## Questions

### Microtrips:

Curently the `Trip` has a placeholder for a microtrip detection algorithm. This can be used to split the trip into smaller segments. The question is how will this be used? Action: Talk to Vangelis Trirakis for WLTC data and microtrip usage for generating a representative cycle.

### Drive Cycles:

STill too early to inquire. 

