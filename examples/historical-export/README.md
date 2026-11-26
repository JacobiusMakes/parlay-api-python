# Load a historical odds CSV into SQLite

Import one saved ParlayAPI closing-lines CSV into a new local SQLite database. Every source column is stored as text, including timestamps, blank observations and the original price strings. This example uses the Python standard library. It makes no network requests.

## Run the workshop

From this directory, run the importer on the three fictional practice rows. Choose a new database filename each time. The destination filesystem must support hard links.

```sh
python load_csv.py practice.csv practice.sqlite
```

Open the result with a SQLite reader and run this query. It counts the rows with at least one missing side for each date and source.

```sql
SELECT game_date, source, COUNT(*) AS delivered_rows,
       SUM(CASE WHEN over_price = '' OR under_price = '' THEN 1 ELSE 0 END)
           AS missing_either_side
FROM closing_lines
GROUP BY game_date, source
ORDER BY game_date, source;
```

| Game date | Source | Delivered rows | Missing either side |
| --- | --- | ---: | ---: |
| 2024-08-16 | practice_book | 2 | 1 |
| 2024-08-17 | practice_book | 1 | 0 |

Read the August 16 row for Sam Example. Its under price is blank. Another player's price and the next day's price describe different observations.

## Use your own saved export

Pass the path of a CSV you are entitled to use and a fresh output filename. An export with only the header creates an empty table. A malformed row fails the import before the new database becomes available. A repeat using an existing destination stops before replacing it.

```sh
python load_csv.py /path/to/your/export.csv private-snapshot.sqlite
```

The ParlayAPI daily prop export is `GET /v1/historical/closing-lines.csv`. It accepts one UTC date per request. Choose the date and filters before using your own account. Preserve the request scope and the response headers `X-Export-Rows` and `X-Export-Credits` with your private source file. A result at the requested limit may represent part of the day. Keep the CSV and database in a private working directory. [Historical coverage](https://parlay-api.com/historical-coverage) · [Data-use terms](https://parlay-api.com/terms)
