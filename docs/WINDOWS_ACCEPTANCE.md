# Windows acceptance: pending until run on Windows

Use an unlocked Windows 10/11 desktop with one enabled monitor, unchanged scaling, ordinary integrity, and no sensitive windows. Do not run this over a disconnected/locked remote session. These tests visibly move the real cursor and type in the harmless lab. Close the main TeachDesk UI before running the native test harness to release its global hotkey. Keep your hands off during automated tests.

## Automated native diagnostics

After setup, in PowerShell from the repository:

```powershell
$env:TEACHDESK_WINDOWS_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest tests/test_windows_native.py -q -s
Remove-Item Env:TEACHDESK_WINDOWS_TESTS
```

Five tests are defined: scoped screen capture with injected-event filtering, and actual OS-hotkey cancellation during motion, typing, held key, and held mouse button. Each launches its own lab. The fixture starts with an editable harmless field focused so text is visible. If Windows refuses foreground activation, click the lab during its five-second focus window and rerun. A conflicting Ctrl+Alt+F8 registration is a failure to fix, not a reason to disable the emergency stop.

The harness uses native input to trigger the real registered emergency chord. It checks cancellation, thread exit, held-input tracking and native A-key state. Core tests additionally check that no new SendInput-equivalent event is accepted after cancellation. Neither test set proves hard real-time latency on all machines, nor does synthetic hotkey activation prove a physical keyboard combination reaches the hook under every driver/layout. Perform the manual physical-hotkey checks below as well.

## Real learning and control protocol

Record actual results, model identifier and Windows/display settings. Do not mark these passed from unit tests or authored fixture graphs.

| Check | Procedure and required evidence |
|---|---|
| Actual teaching capture | Create a fresh task; record a mouse path, left/right clicks, scrolling, ordinary keys with explicit non-sensitive opt-in, a shortcut and a held key in the lab. Pause/resume. The timeline must show physical events and measured hold durations aligned with real frames; excluded/out-of-focus actions must not appear. Stop capturing before reviewing. |
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
