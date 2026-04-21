# Stack Research

**Domain:** Event persistence for distributed trading systems
**Researched:** 2026-04-21
**Confidence:** HIGH

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| ClickHouse | 24.x+ | Columnar event store | High write throughput (100K+ rows/sec), excellent time-series compression, SQL interface, mature Python ecosystem |
| clickhouse-connect | 0.7.0+ | Python HTTP client | Official ClickHouse Inc client, async support, connection pooling, type conversion, streaming queries |
| msgpack | 1.0.5+ (existing) | Serialization | Already used in TycheEngine; preserve for event payload encoding in ClickHouse |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| clickhouse-connect[async] | 0.7.0+ | Async HTTP client | For non-blocking ingestion from ZMQ event threads |
| docker | — | CI testing | Run ClickHouse in Docker for integration tests |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| ClickHouse Local | Local testing without server | Useful for unit tests that don't need full server |
| clickhouse-client | CLI for ad-hoc queries | Debug and schema exploration |

## Installation

```bash
# Add to pyproject.toml [project.optional-dependencies]
persistence = [
    "clickhouse-connect>=0.7.0",
]

# Docker for local dev / CI
docker run -d --name ch-dev -p 8123:8123 -p 9000:9000 clickhouse/clickhouse-server:24
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| clickhouse-connect | asynch | `asynch` is native protocol (faster), but `clickhouse-connect` has better docs, HTTP works through proxies/load balancers, and is officially maintained by ClickHouse Inc. Use `asynch` only if native protocol performance is critical. |
| clickhouse-connect | clickhouse-driver | `clickhouse-driver` is older, sync-only, less maintained. Avoid for new projects. |
| ClickHouse | PostgreSQL + TimescaleDB | TimescaleDB is simpler for smaller scale (<1M events/day) and has better transactional guarantees. ClickHouse wins on raw write throughput and compression for high-frequency market data. |
| ClickHouse | Apache Kafka + consumer | Kafka is a message bus, not a database. Could use Kafka as ingestion buffer + ClickHouse as store, but adds operational complexity. Use only if event volume exceeds single ClickHouse node capacity. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Row-by-row INSERTs | ClickHouse is optimized for bulk inserts; row-by-row is 100x+ slower | Batch inserts (1K-100K rows per batch) |
| JSON/JSONB columns for structured data | Poor query performance, no columnar benefit | Flatten to columns, or use Tuple/Nested types |
| Mutable tables (UPDATE/DELETE) | ClickHouse is append-only; mutations are expensive | Use ReplacingMergeTree or versioned inserts |
| SQLite for production | Cannot handle high-frequency tick data volume | ClickHouse for prod, SQLite only for offline dev fallback |

## Version Compatibility

| Package | Compatible With | Notes |
|-----------|-----------------|-------|
| clickhouse-connect 0.7.x | ClickHouse 22.3+ | Uses HTTP interface; backward compatible with older servers |
| clickhouse-connect 0.7.x | Python 3.8+ | TycheEngine requires 3.9+, so fully compatible |

## Sources

- ClickHouse official docs: https://clickhouse.com/docs — HTTP interface, Python client, table engines
- clickhouse-connect PyPI: https://pypi.org/project/clickhouse-connect/ — API reference, async examples
- ClickHouse knowledge base: Best practices for time-series data, batch sizing, and schema design

---
*Stack research for: Event persistence with ClickHouse*
*Researched: 2026-04-21*
