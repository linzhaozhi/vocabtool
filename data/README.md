# Data Layout

This directory separates raw source files from generated files used by the app.

## Directories

- `source_wordlists/`: raw files downloaded from official or publisher-owned
  sources. Do not edit these by hand.
- `processed/`: generated CSV files used by the Streamlit app.

## Build Flow

Run this from the project root after changing source wordlists or ranking rules:

```bash
python3 tools/build_priority_vocab.py
python3 tools/build_local_card_lexicon.py
```

The app loads `data/processed/ngsl_31k_priority.csv` by default. The metadata
file next to it explains why each word received its rank.
Card generation also loads `data/processed/local_card_lexicon.csv` so local
definitions and available local examples are used before AI fallback.

## Legacy File

`ngsl_sfi_31k.csv` remains in the project root as the original 31k frequency
baseline. The generated priority list keeps that frequency data as its backbone,
then boosts curated learner lists and NGSL supplementary essentials such as
weekdays, months, and numbers.
