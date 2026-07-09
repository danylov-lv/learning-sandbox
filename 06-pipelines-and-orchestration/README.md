# 06 - Pipelines and Orchestration

An Airflow-based ETL pipeline built around idempotency and backfill correctness, alongside dbt for transformation modeling and a comparison against Prefect's execution model. Includes pandera data contracts to catch schema drift before it reaches downstream consumers. Orchestrates the Spark job from module 05 and uses module 02's Postgres instance as a dbt target.

Includes an optional k8s-bonus level: deploying the orchestration stack to a local kind/k3d cluster with a hand-written Helm chart.

Status: not generated yet (see GENERATION_STATE.md)
