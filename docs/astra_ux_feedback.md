# UX Review — GPT-6 Astra (via codex CLI)

Static read-only review of `module/files/remote.html`, `module/files/keystone.js`,
README, and screenshots. Latency/live-device behavior not tested.

## Overall

Solid foundation for a couch remote: dark interface, large primary buttons,
unmistakable OK key, persistent bottom nav. The three recurring problems:
**frequent controls are separated or buried, confirmation that a command
worked is weak, and some touch interactions do something unexpected.**

## D-pad and thumb ergonomics

- `.dpad` is stretched horizontally (117px between button centers vs 74px
  vertically at 390px viewport) — left/right need more thumb travel than
  up/down. A bounded, more-square D-pad would help. (`remote.html:75`)
- Back/Home sit below the D-pad, volume below Media, keyboard access is in
  the header — the most-used controls are scattered while Stats/Align
  permanently occupy bottom-bar space. (`remote.html:299`)
- Direction/volume buttons only listen for `click`, no press-and-hold
  repeat — navigating a long list means repeated tapping. (`remote.html:761`)
- The touchpad has no Back/Home/volume — leaving it to back out of something
  means a tab switch. (`remote.html:360`)

## Touchpad behavior and trust

- **"Center" is misleading** — it only resets the phone's decorative dot,
  sends no projector command. Looks broken. (`remote.html:981`)
- Two-finger scroll can still trigger a click: the right-click timer isn't
  cancelled on a second finger, and `touchcancel` runs the tap-ending logic.
  (`remote.html:919`, `remote.html:964`)
- "Hold" is overloaded — the hint says hold for right-click, but the Hold
  *button* latches left-click for dragging. Needs distinct labels
  ("Drag lock" / "Release drag"). (`remote.html:363`, `remote.html:899`)

## Discoverability and hierarchy

- Apps tab opens with casting instructions before the app launcher itself —
  delays the actual purpose for a daily user. (`remote.html:392`, `:1021`)
- Pinning favorites relies on a small long-press hint with no explicit
  "Edit favorites" action, and pins only sort within their existing
  category. (`remote.html:998`)
- Tools buries ordinary settings behind 13 picture-control sliders before
  power/Bluetooth/maintenance/process-monitor. (`remote.html:553`)
- `showTab()` always scrolls to top — switching tabs and back loses your
  scroll position. (`remote.html:699`)
- "Settings" inside Tools opens Android settings on the projector, not
  in-app settings — rename it. (`remote.html:639`)

## Feedback, latency, error recovery

- The connection dot represents the mouse WebSocket only, turns green right
  after the auth frame — CGI commands can be failing while it stays green.
  (`remote.html:735`)
- `call()` feedback is a 10px ellipsized string in the header with no
  timeout/HTTP-status handling; overlapping requests can overwrite each
  other's messages. (`remote.html:39`, `:752`)
- `wsSend()` queues commands while disconnected *and* callers also send via
  CGI — reconnect can replay/duplicate pointer actions. (`remote.html:744`,
  `:884`)
- Send clears the text field before success is confirmed — a failed request
  loses what was typed. (`remote.html:793`)
- Some status messages render in the wrong card (e.g. Power/Interface Apply
  writes into the preceding picture card's status box, possibly offscreen).
  (`remote.html:1267`, `:1480`)

## Keystone Lab

Photo overlay + manual fallback + explicit Apply confirmation + Restore is a
good design overall. Issues:

- Both "Start with camera" and "Use photo" change the live projection before
  a file is even picked, with no cleanup handler if the picker is cancelled.
  (`remote.html:1616`)
- "Use photo" implicitly assumes the current calibration state — an older
  photo can produce a misleading proposal. (`remote.html:1793`)
- The preview canvas is `touch-action:none` as soon as the overlay draws,
  before "Edit detected points" is pressed — blocks normal scrolling on a
  tall photo. (`remote.html:230`, `:1656`)
- Current/Proposed values are shown as raw firmware coordinates (`LT 48,98`)
  with no visual prediction of the corrected footprint. (`remote.html:539`)
- Detection confidence percentages look more authoritative than the
  underlying heuristic supports. (`keystone.js:213,234,340`)

## Touch sizing / process monitor

- `.ctl button` and process Kill buttons are ~26–29px tall (7px padding) —
  below the 44px targets used elsewhere. (`remote.html:131`, `:145`)
- Process names truncate to hover-only titles; CPU/mem columns have no
  labels; kill confirmation names only the PID, not the process name.
  (`remote.html:1340`, `:1397`)

## Top 5 fixes, ranked by impact/effort

1. **Preserve text until Send succeeds; show an adjacent retryable error.**
   High impact, small effort — eliminates lost input.
2. **Fix touchpad gesture classification; remove/replace the misleading
   Center action.** High impact, small-medium effort.
3. **Surface common destinations immediately** — favorites above casting,
   collapsible Tools sections, preserved tab scroll position.
4. **Press-and-hold repeat + shared Back/Home/volume on the Pad tab.**
   High daily impact, medium effort.
5. **Make Keystone Lab's capture/edit steps explicit** — prepare before
   photographing, keep cancel/restore visible, validate stale-photo
   calibration, keep review mode scrollable.
