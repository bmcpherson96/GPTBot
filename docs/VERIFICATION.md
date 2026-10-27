# Verification record

Build environment: Linux x86_64, Python 3.12.14. No interactive Windows desktop, no user game, no runtime model key. No paid model requests were made.

## Verified in this environment

- Editable installation from the pinned manifest/constraints in a local virtual environment; `pip check` reports no broken dependencies.
- Core/UI test suite: **49 passed, five native Windows tests skipped** in the recorded run. Tests exercise SQLite persistence and crash interruption, synchronized recording/event/hold data, ordinary-key redaction, exclusion masking, failure finalization, real OpenCV target relocation and ambiguity rejection, malformed/unsafe workflow rejection, source/held-out isolation, visual transition and completion checks, separate held-out practice, branch/expected-stop coverage, bounded loops, candidate isolation/promotion/rollback, invalidation/deletion, intervention accounting with optional pausing, timing/path memory, model request/consent/error contracts, Qt library/timeline/review/reopen and lab behavior.
- Cancellation tests run a worker and an independent stop caller during movement, text input, key holds and mouse holds. They verify held-state release, worker termination and refusal of subsequent queued input. **The desktop backend is a test double**, so these do not establish native Windows stop latency or driver behavior.
- The model contract tests exercise the real request/response construction and candidate pipeline using an explicitly mocked HTTP transport. **They do not establish that a real model learned the task.** Production has no mock model fallback, no preloaded skill and no automatic promotion of a model response.
- Qt UI and separate lab render with the offscreen Qt platform. Their widget interactions and reopen behavior execute in tests. This does not establish Windows capture or input behavior.
- Windows x64/Python 3.12 wheels for all chosen runtime distributions and applicable transitive dependencies were downloaded successfully using verified TLS. The cross-download used an explicit package list with `--no-deps` because pip evaluated pynput's Linux evdev environment marker on the Linux host even with `--platform win_amd64`. This confirms artifact availability, not a Windows installation or import test.
- Official source/distribution interfaces checked as listed in `ARCHITECTURE.md`.

## Still unverified / not implemented

| Area | State |
|---|---|
| Native Windows capture, physical hooks, SendInput, actual hotkey, DPI/session/scope behavior | Implemented; five opt-in tests supplied, **not run here** |
| Real model learning, crop quality, clarification quality, actual token cost | Implemented configurable transport; **not exercised with a real credential/model** |
| Real model-generated lab task at a changed layout | **Pending Windows/model acceptance protocol** |
| User's game | Unavailable; no compatibility or task competence claim |
| Broad semantic perception/OCR and autonomous recovery | Not implemented |
| Statistical personal-style resemblance benchmark | Not implemented; basic separate path/timing extraction and execution exist |
| Automatic password detection, encrypted vault/recordings, forensic secure deletion | Not implemented; manual pause/masks/redaction and ordinary local deletion exist |
| Speech explanations | Not implemented; typed timestamped explanations exist |
| Signed executable/installer | Not built; Python source and PowerShell setup/launch supplied |
| CI/native Windows test result | Workflow definition supplied; no remote CI result claimed |

Run `python -m pytest -q -r s` in the prepared virtual environment to see exact current pass/skip counts. Follow `WINDOWS_ACCEPTANCE.md` for the remaining native and real-model gates. Do not substitute hand-authored fixture tests for learning evidence.
