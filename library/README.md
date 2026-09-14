# library/

## Track lists (start here)
Drop playlist exports as .txt or .csv in this folder. Any of these work:
  - Google Takeout CSV (takeout.google.com -> YouTube and YouTube Music)
  - copy-paste from the web player
  - hand-typed

Format: one track per line. `Artist - Title` is ideal, but the parser is
lenient — it will handle "Title - Artist", numbered lists, and CSV columns.

## audio/
Audio files for the SHORTLIST only. Do not bulk-download a whole playlist;
send the track list first so it can be triaged and prioritised.

Anything here gets indexed: tempo (regression-fit), key, per-bar downbeats
(beat_this), structure, vocal syllable density, band balance, and Demucs stems.
Once indexed, "what fits this role?" becomes a search over measured properties
rather than recall.
