# Second Tool Spec Scaffold

Use this file to define the second Parabix tool I/O behavior (for example `editd`, `wc`, or `ucount`).

## Required sections

1. Supported parameters and values
2. Exit code definitions (`0`, `1`, `2` or tool-specific)
3. Expected stdout/stderr format
4. Error-case behavior
5. Oracle mapping rules

This project scaffold already supports plugging in another tool by adding:

- a new frame CSV
- command builder + oracle function in `scripts/run_combinatorial_tests.py`
