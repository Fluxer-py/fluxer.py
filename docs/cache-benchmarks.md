# Cache benchmark results

Run the offline workload from the library directory:

```sh
python benchmarks/cache.py
```

To compare another checkout, pass the directory containing its `fluxer` package:

```sh
python benchmarks/cache.py /path/to/baseline/package-root
```

The baseline below is commit `90933cb0ea4381f62e734c5ddb142346db4429b2`.
Both runs used Python 3.13.12 on the same Windows environment. They ran
sequentially, with mocked command execution and no network access.

| Measurement | Baseline | Refactor |
| --- | ---: | ---: |
| Retained author objects for 1,000 messages from one user | 1,000 | 1 |
| Retained traced bytes after those messages | 1,941,495 | 1,127,950 |
| Peak traced bytes | 2,024,755 | 1,151,918 |
| Retained allocation blocks | 20,862 | 13,967 |
| Parses for one bot message | 2 | 1 |
| Dispatch 1,000 client messages, with tracing enabled | 126.58 ms | 147.54 ms |
| Update one guild 200 times, no unrelated guilds | 3.18 ms | 5.66 ms |
| Same updates, 1,000 unrelated guilds | 8.36 ms | 5.89 ms |
| Same updates, 5,000 unrelated guilds | 30.48 ms | 5.52 ms |

The workload retained about 42% fewer traced bytes. Guild updates no longer
scan unrelated guild channels, and bot messages are parsed once. The added
identity management and indexes have a fixed cost: the small-client operations
in this sample took longer. These are illustrative single-run measurements,
not throughput guarantees or statistical performance thresholds.

`tracemalloc` counts Python allocations still retained at measurement time;
it does not report process RSS or cumulative allocations. The message workload
uses one repeated author and simple text, so results will differ with many
distinct authors, attachments, snapshots, and application-held references.

The benchmark prints JSON so repeat runs can be saved and compared. Correctness
tests separately cover retention limits, cleanup, snapshot isolation, entity
identity, and cache progress while a command remains blocked.
