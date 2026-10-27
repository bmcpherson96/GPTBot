# Verification record

Build environment: Linux x86_64, Python 3.12.14. No interactive Windows desktop, no user game, no runtime model key. No paid model requests were made.

## Verified in this environment

- Editable installation from the pinned manifest/constraints in a local virtual environment; `pip check` reports no broken dependencies.
- Version 0.1.3 core/UI/regression suite: **84 passed, seven native Windows tests skipped**. New UI regressions verify selecting the just-finished recording, opening its timeline and first-frame preview, keeping interrupted recordings visibly interrupted, clearing stale previews when no frame exists, and preserving manual history selection during routine refreshes. The added checks simulate minimizing or covering the target while its foreground handle remains unchanged, focus loss, movement/resizing during capture, physical-pixel context establishment/restoration, last-valid-frame preservation and pausing, execution pausing, and blocking older evidence before transmission. The existing suite covers storage, workflows, readiness, cancellation, model contracts and UI behavior.
- Cancellation tests run a worker and an independent stop caller during movement, text input, key holds and mouse holds. They verify held-state release, worker termination and refusal of subsequent queued input. **The desktop backend is a test double**, so these do not establish native Windows stop latency or driver behavior.
- The model contract tests exercise the real request/response construction and candidate pipeline using an explicitly mocked HTTP transport. **They do not establish that a real model learned the task.** Production has no mock model fallback, no preloaded skill and no automatic promotion of a model response.
- Qt UI and separate lab render with the offscreen Qt platform. Their widget interactions and reopen behavior execute in tests. This does not establish Windows capture or input behavior.
- Windows x64/Python 3.12 wheels for all chosen runtime distributions and applicable transitive dependencies were downloaded successfully using verified TLS. The cross-download used an explicit package list with `--no-deps` because pip evaluated pynput's Linux evdev environment marker on the Linux host even with `--platform win_amd64`. This confirms artifact availability, not a Windows installation or import test.
- Official source/distribution interfaces checked as listed in `ARCHITECTURE.md`.

## Evidence from the user's Windows PC

Screenshots from Windows/Python 3.12.10 show the original release installed successfully, `pip check` reported no broken requirements, and **49 core tests passed with five native tests skipped**. TeachDesk and the Lab launched, and a demonstration saved frames and input events. Inspecting its final frame exposed desktop wallpaper and the controller rather than the Lab. The user reported minimizing the Lab after completion. A minimization race is plausible: the original capture path rechecked only foreground HWND after acquisition, not visibility/minimized state and geometry. This does not establish that all earlier frames were correct or exclude a coordinate-context problem.

Version 0.1.1 adds complete pre/post scope checks, physical window-center ownership, scoped physical-pixel DPI contexts and physical cursor queries. Unavailable targets pause capture instead of saving the invalid frame or losing previously valid evidence. Older demonstrations are retained but blocked from model use/practice/readiness. These changes pass simulated regression checks; a new Windows preview and native checks were still required to verify that attempted repair on the user's machine. No real model request has been made.

The user subsequently launched version 0.1.1 successfully through the CMD launcher with tasks preserved. A supplied screen recording shows manual Lab completion and a pause when returning to the controller. A new demonstration preview shows the Lab, but begins during typing after item selection; it does not verify capture of the full task from its initial state. Version 0.1.2 fixes the controller retaining the old timeline selection after recording. That UI change is tested offscreen and still needs a Windows user check. The native tests and real-model learning remain pending.

The next supplied Windows screenshots, from version 0.1.2 and demonstration `2a25d455`, show READY at 0.068s, COMPLETE at 9.354s, then **wallpaper/controller content at 10.566s**, before capture-paused events at 10.836/11.049s. The user reports not using Alt+Tab. Thus the previous scope checks did not fix the transition defect; the screenshots establish that limitation without proving exactly which Windows animation/state race caused it. Do not send that recording to a model.

Version 0.1.3 replaces pixel acquisition with exact-HWND Windows Graphics Capture, uses physical DWM visible bounds, enforces exact frame-size agreement, and blocks all prior desktop-crop recordings through capture-validation version 3. New mocked-provider tests verify HWND-only configuration, no desktop fallback, row-padding/BGRA conversion and owned-frame lifetime, timeout/closure/error cleanup, bounds failures, and rejection of old evidence before HTTP. The additional native covering-window diagnostic must verify the actual provider cannot capture a magenta overlay. These are implemented and tested with doubles on Linux; **the new Windows backend has not been executed here or on the user's machine yet**.

## Still unverified / not implemented

| Area | State |
|---|---|
| Native Windows capture, physical hooks, SendInput, actual hotkey, DPI/session/scope behavior | Implemented; seven opt-in tests supplied, **not run here**; capture defect observed through 0.1.2; replacement backend not yet run on Windows |
| Real model learning, crop quality, clarification quality, actual token cost | Implemented configurable transport; **not exercised with a real credential/model** |
| Real model-generated lab task at a changed layout | **Pending Windows/model acceptance protocol** |
| User's game | Unavailable; no compatibility or task competence claim |
| Broad semantic perception/OCR and autonomous recovery | Not implemented |
| Statistical personal-style resemblance benchmark | Not implemented; basic separate path/timing extraction and execution exist |
| Automatic password detection, encrypted vault/recordings, forensic secure deletion | Not implemented; manual pause/masks/redaction and ordinary local deletion exist |
| Speech explanations | Not implemented; typed timestamped explanations exist |
| Signed executable/installer | Not built; Python source, PowerShell scripts and a double-click CMD setup/launcher supplied; CMD startup observed on the user’s Windows PC for 0.1.1 |
| CI/native Windows test result | Workflow definition supplied; no remote CI result claimed |

Run `python -m pytest -q -r s` in the prepared virtual environment to see exact current pass/skip counts. Follow `WINDOWS_ACCEPTANCE.md` for the remaining native and real-model gates. Do not substitute hand-authored fixture tests for learning evidence.
