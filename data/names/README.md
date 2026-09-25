# Name lists

The lists the anonymisation pass draws pseudonyms and places from, and the fresh-name reserve draws
from. The two name lists are works of the US federal government and carry no copyright; the postal
code file is GeoNames data under CC BY 4.0.

| file | what | source |
|---|---|---|
| `ssa_atleast100.txt` | 7,304 first names, one per line: every name given to 100 or more babies in some year | Social Security Administration, "Beyond the Top 1000 Names", https://www.ssa.gov/oact/babynames/limits.html (names.zip), filtered to count >= 100 |
| `census/Names_2010Census.csv` | 162,254 surnames with counts, the surnames occurring 100 or more times in the 2010 Census | US Census Bureau, "Frequently Occurring Surnames from the 2010 Census", https://www.census.gov/topics/population/genealogy/data/2010_surnames.html |
| `uszip/US.txt` | US postal codes with city and state, 41,490 rows | GeoNames, https://download.geonames.org/export/zip/ (US.zip), Creative Commons Attribution 4.0, credit to www.geonames.org |

The postal codes keep a replaced ZIP valid for the city it sits next to: replacing Houston's 77002
with five random digits would give a Houston address a ZIP no Houston has.

`scripts/name_registry.py` reads all three (the census pool: first names × surnames, about 1.2 billion
combinations); `scripts/fresh_names.py` draws the reserve of names that occur nowhere in the release.
