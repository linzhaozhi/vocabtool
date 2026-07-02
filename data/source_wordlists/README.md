# Source Wordlists

Downloaded on 2026-07-02 from official or publisher-owned sources for local
ranking experiments. Keep these files as raw inputs; write normalized or merged
outputs elsewhere.

## NGSL Project

Source page: https://www.newgeneralservicelist.com/new-general-service-list

Files:
- `ngsl/NGSL_1.2_stats.csv`
- `ngsl/NGSL_1.2_alphabetized_description.txt`
- `ngsl/NGSL_1.2_lemmatized_for_teaching.csv`
- `ngsl/NGSL_1.2_lemmatized_for_research.csv`
- `ngsl/NGSL_1.2_with_English_definitions.xlsx`
- `ngsl/NGSL_1.2_plus_stats_and_frequencies_to_31k.xlsx`
- `ngsl/NGSL_1.2_supplementary_words.csv`
- `ngsl/source_page.html`

## Oxford Learner's Dictionaries

Source page: https://www.oxfordlearnersdictionaries.com/wordlists/oxford3000-5000

Files:
- `oxford/The_Oxford_3000.pdf`
- `oxford/The_Oxford_3000_by_CEFR_level.pdf`
- `oxford/The_Oxford_5000.pdf`
- `oxford/The_Oxford_5000_by_CEFR_level.pdf`
- `oxford/American_Oxford_3000.pdf`
- `oxford/American_Oxford_3000_by_CEFR_level.pdf`
- `oxford/American_Oxford_5000.pdf`
- `oxford/American_Oxford_5000_by_CEFR_level.pdf`
- `oxford/source_page.html`

## NGSL Special Purpose Lists

Source pages:
- https://www.newgeneralservicelist.com/new-academic-word-list
- https://www.newgeneralservicelist.com/toeic-service-list
- https://www.newgeneralservicelist.com/business-service-list

Files:
- `ngsl_special_purpose/NAWL_1.2_stats.csv`
- `ngsl_special_purpose/NAWL_1.2_alphabetized_description.txt`
- `ngsl_special_purpose/NAWL_1.2_lemmatized_for_teaching.csv`
- `ngsl_special_purpose/NAWL_1.2_lemmatized_for_research.csv`
- `ngsl_special_purpose/NAWL_1.2_with_English_definitions.csv`
- `ngsl_special_purpose/NAWL_1.2_learning_dictionary.html`
- `ngsl_special_purpose/TSL_1.2_stats.csv`
- `ngsl_special_purpose/TSL_1.2_alphabetized_description.txt`
- `ngsl_special_purpose/TSL_1.2_lemmatized_for_teaching.csv`
- `ngsl_special_purpose/TSL_1.2_lemmatized_for_research.csv`
- `ngsl_special_purpose/TSL_1.2_definitions.xlsx`
- `ngsl_special_purpose/TSL_1.2_learning_dictionary.html`
- `ngsl_special_purpose/BSL_1.2_stats.csv`
- `ngsl_special_purpose/BSL_1.2_alphabetized_description.txt`
- `ngsl_special_purpose/BSL_1.2_lemmatized_for_teaching.csv`
- `ngsl_special_purpose/BSL_1.2_lemmatized_for_research.csv`
- `ngsl_special_purpose/nawl_source_page.html`
- `ngsl_special_purpose/tsl_source_page.html`
- `ngsl_special_purpose/bsl_source_page.html`

## Cambridge English

Source pages:
- https://www.cambridgeenglish.org/exams-and-tests/preliminary/
- https://www.cambridgeenglish.org/exams-and-tests/key/

Files:
- `cambridge/Cambridge_B1_Preliminary_vocabulary_list.pdf`
- `cambridge/b1_preliminary_source_page.html`
- `cambridge/a2_key_source_page.html`

Note: the current B1 Preliminary PDF was saved from
`https://www.cambridgeenglish.org/images/84669-pet-vocabulary-list.pdf`.
The likely old A2 Key PDF path returned 404 during this download pass, so no A2
vocabulary PDF was saved.

## VOA Learning English

Source file:
- https://docs.voanews.eu/en-US-LEARN/2014/02/15/7f8de955-596b-437c-ba40-a68ed754c348.pdf

Files:
- `voa/VOA_Learning_English_Word_Book.pdf`

## Longman

Source page:
- https://www.ldoceonline.com/

Files:
- `longman/source_page.html`

Note: Longman Dictionary of Contemporary English Online has per-entry frequency
and communication labels, but no official bulk Longman Communication 9000
download was found in this pass. Keep Longman out of automated weighting unless
we later add a confirmed official export or explicitly decide to crawl entry
metadata.

## Princeton WordNet

Source file:
- https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/corpora/wordnet.zip

Files:
- `wordnet/wordnet.zip`

Use: local English definitions and local usage examples for card generation.
The zip includes `wordnet/LICENSE`; keep the license with the raw source file.

## Use Notes

These sources have different licensing and redistribution terms. Use the raw
files for local ranking experiments, and check publisher permissions before
shipping derived wordlists publicly.
