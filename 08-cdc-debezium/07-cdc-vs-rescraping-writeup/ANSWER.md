# CDC vs Re-scraping — Analysis

Fill in each section with your own analysis grounded in your scraper experience and what you've learned from building the CDC pipeline in this module.

## The re-scraping / re-query baseline

*Describe your current polling approach: frequency, cost per poll, what changes you miss between intervals, how you handle deletes, and what it costs your infrastructure.*

## Where CDC wins

*Map each pain point from polling to a concrete CDC capability: low-latency propagation, no missed intermediate state, WAL as the source of truth, delete capture, and snapshot backfill. When would you choose CDC?*

## Where CDC is overkill / the wrong tool

*List scenarios where periodic polling is simpler, cheaper, or necessary: small or low-churn data, third-party websites you can only scrape, no database access, or when operational burden isn't justified. When would you stick with polling?*

## The operational cost of CDC

*Explain the hidden costs: replication slots pinning the WAL (and the cost of retention), Kafka Connect infrastructure and operations, schema evolution discipline, snapshot cost on large tables. What operational burden does CDC introduce?*

## Verdict

*Write the one-sentence decision rule: on what characteristics of a data source would you reach for CDC vs polling? Be concrete — think of a real scraper target and say whether you'd use CDC or polling for it and why.*
