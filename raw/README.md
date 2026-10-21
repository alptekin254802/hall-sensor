# Raw measurements

Each folder holds one capture and is named by its capture ID. [`captures.csv`](captures.csv)
lists all captures with their analysis group, role, acquisition code and load;
`raw_index.json` gives the same records with file hashes.

`load_g` is the reference mass in grams when one load applies to the whole record.
It is blank for records with several load steps, press series and checks, whose
loads are given in `analysis/`. Groups and file columns are described in
[the data dictionary](../DATA_DICTIONARY.md).

Files are gzip-compressed CSVs and can be read directly, for example with
`pandas.read_csv("samples.csv.gz")` or `data_access.py`.
