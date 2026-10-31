# sentiment-claim-audit

Version 0.1.0 is an offline static auditor of documented claims about text polarity processing. It compares root README.md and Markdown under any docs directory with provider-resolved Python AST evidence. It never executes inspected source.

Install with `pip install .` and run:

```sh
sentiment-claim-audit /path/to/project
python3 -m sentiment_claim_audit /path/to/project --json
python3 -m sentiment_claim_audit /path/to/project --verbose --ignore vendor --fail-on MEDIUM
```

The optional flags are `--json`, `--verbose`, repeatable `--ignore PATH_PREFIX`, `--fail-on LOW|MEDIUM|HIGH` (default HIGH), and `--version`. Ignore prefixes are relative to the root and match complete path components. Output goes to standard output; errors go to standard error. Exit status is 0 for no findings at the configured threshold, 2 for findings at that threshold, and 1 for usage or I/O errors. JSON includes status, findings, and production/test evidence paths. A MEDIUM finding still has FAIL status even when the default threshold permits exit 0.

The auditor recognizes Transformers task literals and dedicated pipeline construction, bound VADER calls, and TextBlob result access. Provider imports and aliases are resolved within individual modules. Local definitions and parameters shadow imports. Evidence can cross methods through self attributes. Test evidence produces a MEDIUM finding when production evidence is absent; contradictory production evidence and unsupported positive claims produce HIGH findings.

Fenced code is excluded from documentation; inline code is included. Paragraph matching normalizes case, contractions, hyphens, and whitespace. Negative spans are removed before positive matches. Source in fixtures, docs, and examples is excluded. Test directories and test filename conventions are classified separately. Symlinks are excluded and invalid Python supplies no evidence.

This is a static heuristic, not a guarantee of runtime correctness or model quality. Dynamic imports, runtime factories, and inter-module data flow are outside its scope. No network access or file writes are performed by the auditor.

Development: run `python3 -m unittest discover`, then `python3 -m build` for isolated distribution builds. MIT licensed; see LICENSE.
