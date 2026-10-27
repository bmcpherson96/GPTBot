# Windows acceptance: pending until run on Windows

Use an unlocked Windows 10 2004+/11 (x64) desktop with one enabled monitor, unchanged scaling, ordinary integrity, and no sensitive windows. Do not run this over a disconnected/locked remote session. These tests visibly move the real cursor and type in the harmless lab. Close the main TeachDesk UI before running the native test harness to release its global hotkey. Keep your hands off during automated tests.

## Automated native diagnostics

After setup, in PowerShell from the repository:

```powershell
$env:TEACHDESK_WINDOWS_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest tests/test_windows_native.py -q -s
Remove-Item Env:TEACHDESK_WINDOWS_TESTS
```

Seven tests are defined: scoped screen capture with injected-event filtering and expected Lab-surface colors, HWND-source isolation while a solid-magenta window covers the Lab, rejection of a minimized-window capture, and actual OS-hotkey cancellation during motion, typing, held key, and held mouse button. Each launches its own lab. The covering-window test deliberately calls only the image provider while the Lab is covered; production retains the foreground/scope guards. The test must still receive Lab pixels, not the magenta cover. This checks image-source isolation separately from possibly delayed window-state APIs. The fixture starts with an editable harmless field focused so text is visible. If Windows refuses foreground activation, click the lab during its five-second focus window and rerun. A conflicting Ctrl+Alt+F8 registration is a failure to fix, not a reason to disable the emergency stop.

The harness uses native input to trigger the real registered emergency chord. It checks cancellation, thread exit, held-input tracking and native A-key state. Core tests additionally check that no new SendInput-equivalent event is accepted after cancellation. Neither test set proves hard real-time latency on all machines, nor does synthetic hotkey activation prove a physical keyboard combination reaches the hook under every driver/layout. Perform the manual physical-hotkey checks below as well.

## Project interface check

Version 0.2.0 should open on Projects. Open an existing project, verify its saved recording in Review with Beginning/End, navigate to Details and back, and close/reopen with the same library. A new project starts at 0% until checks are satisfied. Confirm Stop stays accessible during the start countdown and recording/running; opening a project must never begin capture, a paid AI request, or desktop input. Teaching a practice example from Practice / Run must store a practice-role recording, not add it to the model evidence. The original detailed controls remain available under Settings → Project details for the checks below.

## Model-format and saved-reply check (0.2.1)

Open the existing project without changing its goal or valid recording. Existing OpenAI settings should default to structured replies. A fresh Learn Project attempt is a new paid request and must show the usual transmission confirmation. Verify the actual endpoint accepts the generated schema and returns a candidate that passes crop/semantic validation. Inspect any rejected text in Details → AI replies; do not call it learned. The reply/usage should remain after restart. Check Saved Reply must make no HTTP request and never auto-promote. Changing an answer, goal or excluded frame must block reuse of the older response. Delete a source/project and verify related replies disappear. Confirm the error dialog's header no longer claims model review is still in progress. Do not reuse key values or full private replies in screenshots.

## Real learning and control protocol

Record actual results, model identifier and Windows/display settings. Do not mark these passed from unit tests or authored fixture graphs.

| Check | Procedure and required evidence |
|---|---|
| Actual teaching capture | Create a fresh task; record a mouse path, left/right clicks, scrolling, ordinary keys with explicit non-sensitive opt-in, a shortcut and a held key in the lab. Pause/resume. The timeline must show physical events and measured hold durations aligned with real frames; excluded/out-of-focus actions must not appear. Stop capturing before reviewing. |
| Minimize/focus-transition regression (0.1.3) | Record a fresh Lab demonstration to COMPLETE, wait two seconds, then minimize the Lab and return to TeachDesk to Stop. The final saved frame must still show the Lab's COMPLETE state, with no wallpaper/controller frame replacing it. Repeat by clicking the controller/taskbar, minimizing, using Alt+Tab, and moving/resizing during capture; affected in-flight frames must be discarded. Check first and final previews at your actual scaling. These new checks remain unrun in the cloud environment. |
| Real model integration | Configure your own vision endpoint/key and consent. Generate from the actual training recording. Inspect that all target crops refer to included training screenshots, goal/scope are correct, completion is distinct, and there are no more than three important questions. Record provider usage/charge. Invalid crops are a failed model attempt, not success; refine the demonstration, answers, prompt or candidate and retry transparently. |
| Clarification semantics | If a blocking question exists, save an answer. Practice must still be blocked until regeneration incorporates it into a new candidate. Verify answers persist across restart and appear in follow-up model context. For an unambiguous demonstration, zero questions is a valid result. |
| Movement beyond replay | Shuffle the lab controls after training. Record a separate held-out completion example, then reset without reshuffling. Practice that model-generated candidate; it must find the relocated button/field by appearance, type oak, finish, and independently detect COMPLETE. Confirm the recorded variation evidence and actual visible cursor destinations. Training coordinates must not drive the run. |
| Physical emergency during motion | Use a candidate with a sufficiently long safe pointer movement. Press physical Ctrl+Alt+F8 mid-move. The cursor must stop issuing new moves; run outcome must be stopped, not verified. Check actual held-state release and evidence. |
| Physical emergency during typing | Practice a harmless longer input in the diagnostic lab or a separately taught local scratch editor. Press the emergency chord mid-text. No suffix should be typed after cancellation. Clear/reset manually before another run. Never test in chat, a terminal or a consequential form. |
| Held-key and held-button stop | On harmless scope, test the native diagnostics and physical hotkey with a candidate holding a key/drag. No key/button may remain down after stop. If release fails, the app must report failure; inspect the actual desktop state. Do not count these as completions. |
| Manual intervention | During practice, physically move the mouse. Confirm Paused and release. Correct the expected current step, click Resume, focus the target in five seconds. Continuation must verify the interrupted step's postcondition; it must not replay partial text/clicks. Missing postcondition stops. Even a completed intervention run must not satisfy readiness. |
| Completion protection | Start from already COMPLETE: reject before input. Start with **Unexpected state** checked: stop on missing starting condition. Duplicate a target visually if possible: reject ambiguity. A timeout must not become success. |
| Display/window scope | Try another selected app, wrong title, minimized/partly off-screen window, multiple monitors, changed scaling, focus loss and movement/resize during input. Each must block or pause with a useful reason. Returning focus/resuming must recheck scope before action. Do not attempt UAC or elevated targets. |
| Necessary branches and bounds | For a genuinely conditional taught task, supply held-out examples for both outcomes. An intentional stop path needs a held-out expected-stop example. One successful branch must not grant full readiness. A persistent decision loop must stop at eight visits or 80 nodes, and a paused run must still respect its duration. |
| Readiness and library | Verify six individual checks and their evidence; 100% means checklist completion only. The first validated version becomes active/Ready; missing practice or an unresolved question stays Learning. Performance and style measurements remain separate. |
| Correction and rollback | Add a recovery demonstration or edit a candidate. It must not replace the active version automatically. Validate it separately, promote, then restore the prior still-valid version. Verify both histories remain. Deleting source evidence must remove/invalidate derived eligibility. |
| Persistence/crash | Close/reopen after recording/review/practice and check task, frames, timeline, graph, answers, active/prior versions and counts. Terminate during a diagnostic session, reopen: it must be interrupted and must not run automatically. Only do this in the harmless lab; a forcibly killed process cannot guarantee key-release cleanup. |
| Privacy | No new screenshots/event rows outside explicitly enabled sessions. Mask a distinctive label, then inspect full-resolution files: black before save/upload. With masks, ordinary text must remain redacted even if opted in. Cancel model consent: no request. Delete demo/history: files and dependent eligibility must disappear; ordinary deletion is not forensic erasure. |

The existing game is outside the verified scope until its own representative demonstrations, visual predicates, exception behavior and held-out practice pass. Do not assume a successful lab transfers competence to the game.
