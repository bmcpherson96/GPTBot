# Architecture and implementation stages

Python 3.12 keeps image/perception/model work close to well-supported libraries. Qt Widgets via PySide6 Essentials provides a real Windows desktop UI without a browser runtime. SQLite avoids an external database. A separate Windows adapter confines capture, hooks, session checks and native input; the rest can be tested on Linux.

| Component | Source | Responsibility |
|---|---|---|
| Desktop UI | `teachdesk/ui.py` | Library, review/questions, timeline, candidate editor, authorization, state overlay, worker lifecycle |
| Recording | `teachdesk/recording.py` | Explicit sessions, monotonic event/frame clock, 4fps frames, 20Hz motion samples, holds, privacy defaults, bounded queues |
| Desktop adapter | `teachdesk/windows.py` | Physical pixels, single-monitor/session/scope checks, mss capture, physical-only pynput hooks, SendInput, separate OS hotkey thread |
| Memory | `teachdesk/storage.py` | Transactional local task/demo/event/frame/version/run/audit storage, persistent answers, version promotion, deletion/invalidation |
| Perception | `teachdesk/perception.py` | Source-evidence cropping, contrast checks, translated template recognition, ambiguity rejection |
| Model/review | `teachdesk/model.py` | Consent and configuration, selected evidence retrieval by task, answer reuse, real HTTP model request, untrusted JSON validation |
| Readiness | `teachdesk/workflow.py` | Graph contract and explicit evidence checklist; no confidence score |
| Execution/recovery | `teachdesk/execution.py` | Observe → branch/decide → gated visible input → visual verification; bounded graph traversal, correction pause, cancellation/release, outcome evidence |
| Controlled app | `teachdesk/lab.py` | Independent harmless application with movable controls, multiple observable states and an unexpected-state toggle |

The workflow is a graph, not an input-event replay. Nodes reference named visual targets cropped from included training frames. A node records its evidence and whether its rule is demonstrated or inferred. Graph metadata includes goal, named inputs, starting/completion predicates, supported scope, assumptions, exceptions and prioritized questions. Decisions are local graph decisions, not an online model chain. There are no shell/API action nodes. A new model response never writes source code or promotes itself.

Train/practice roles are established before capture. Practice evidence is not sent to the model. Versions are immutable documents; answers/review status are separate. Editing saves a new candidate. Promotion checks readiness in a transaction and retains prior versions. Intent edits, evidence exclusions/deletion and practice deletion invalidate relevant eligibility rather than fabricating a successful learning history. A crash marks in-progress sessions interrupted at the next launch. Qt's lock file prevents competing application instances for one store.

The runtime model is used only to construct candidates. Relevant examples are retrieved by task and role, then sampled at action-adjacent and time-spaced frames, with the selection disclosed. This is structured memory/context reuse, **not** fine-tuning or weight training. There is no vector database or cross-task semantic retrieval yet.

## Stages

1. **Implemented vertical slice:** create task, local synchronized demonstrations, timeline, real configurable vision-model request and bounded graph contract, important-question answers and regeneration, visual execution adapter, emergency controls, persistence, movable-target lab. Core behavior is tested; the native Windows/model gates below remain open.
2. **Implemented expansion:** multiple training/held-out examples, exclusions and mistake intervals, task library/readiness, branch coverage and bounded loops, correction pauses, candidate isolation/promotion/rollback, performance history, local failure evidence, basic separately learned interaction timing/path profiles. Statistical style fidelity and real Windows performance remain unverified.
3. **Next gate:** run the native Windows checks and the real model-generated lab protocol. Collect actual frame alignment, stop latency, template robustness and model box/clarification failures. Fix demonstrated defects before supporting the user's game. This requires an interactive Windows machine and a configured vision endpoint; Linux/mock transport cannot establish these claims.
4. **Later product work:** reviewed accessible/semantic perception, robust text-variable predicates and cropping UI, representative task-specific retrieval beyond bounded prompts, explicit visual recovery/subworkflow authoring, stronger privacy/field exclusions, style evaluation against reserved trajectories, richer application authorization policies, packaging/signing and monitored deployment. No implementation of these is claimed.

## Official interfaces checked

At build time, direct documentation hosts were inaccessible from the cloud network. Official project documentation/source mirrors on GitHub and official PyPI distribution metadata were retrieved with TLS verification intact:

- [OpenAI official Python Chat Completions resource](https://github.com/openai/openai-python/blob/main/src/openai/resources/chat/completions/completions.py): messages, image content, JSON response mode and `max_completion_tokens`. The app uses HTTP via httpx, not an assumed SDK version or ChatGPT subscription.
- [Microsoft SendInput reference](https://github.com/MicrosoftDocs/sdk-api/blob/docs/sdk-api-src/content/winuser/nf-winuser-sendinput.md): INPUT size, per-event return counts, held state and UIPI limits.
- [Microsoft RegisterHotKey reference](https://github.com/MicrosoftDocs/sdk-api/blob/docs/sdk-api-src/content/winuser/nf-winuser-registerhotkey.md): thread message queue and MOD_NOREPEAT; F12 is reserved, so the app uses Ctrl+Alt+F8.
- [Microsoft SetThreadDpiAwarenessContext](https://github.com/MicrosoftDocs/sdk-api/blob/docs/sdk-api-src/content/winuser/nf-winuser-setthreaddpiawarenesscontext.md), [GetWindowRect](https://github.com/MicrosoftDocs/sdk-api/blob/docs/sdk-api-src/content/winuser/nf-winuser-getwindowrect.md), and [GetPhysicalCursorPos](https://github.com/MicrosoftDocs/sdk-api/blob/docs/sdk-api-src/content/winuser/nf-winuser-getphysicalcursorpos.md): the 0.1.1 capture fix scopes DPI awareness on each calling thread and restores it; window-rectangle virtualization and invisible resize borders are accounted for in supported placement, and cursor positions use the physical API.
- [pynput official FAQ](https://github.com/moses-palmer/pynput/blob/master/docs/faq.rst): Windows event filtering. Returning false filters a listener callback, not the user's OS input; the app never suppresses physical input.
- [python-mss official project](https://github.com/BoboTiG/python-mss) and [Qt PySide6 metadata](https://pypi.org/project/PySide6/): distribution/API usage. `PySide6-Essentials` supplies the actual QtCore/QtGui/QtWidgets modules used.
- Current PyPI JSON release metadata for each pinned runtime dependency was checked. Windows x64 wheel availability is checked separately from running those wheels on Windows.
