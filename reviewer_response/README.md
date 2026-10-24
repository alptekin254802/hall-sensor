# Reviewer-response analysis

Reviewer-response analysis (Reviewer 4, comment 1); not reported in the manuscript.

From the package root, run:

```sh
python reviewer_response/offset_absolute_errors.py
```

The script recomputes and checks `offset_absolute_errors.json`. To regenerate
that file explicitly, add `--write`.

The frozen four-channel interpolation converts the unloaded mean minus the
offset-record mean to force. The signed error is this force minus the known
mass times 0.00980665 N/g; MAE and maximum absolute error use its magnitude.
Unloaded references use 5–10 s and offset records use 10–20 s, with half-open
windows measured from each recording's first sample.

The primary unloaded reference is `43902f60258f44b193994385c76ce99d`
(15 October, 19:13, UTC+3). The alternative is
`8a41d11b7403432fa562c11860d39efc` (19:12). Both are supplied as losslessly
compressed CSVs in `raw/`, indexed as group `RR_D_zero` with role
`reviewer_response_only`.

The 43 offsets are the 16 positions in each first block (542 and 1042 g),
plus 11 positions in the second 542 g block: all ±Y positions and
−X5, −X10 and −X15. The second 1042 g block and the second 542 g block's
−X20 and +X positions are outside this analysis. The selected offset CSVs
are already included in group `D`; the manuscript's center-referenced
position analysis is unchanged.
