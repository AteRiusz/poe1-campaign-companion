# PoE1 Campaign Speedrun Companion

A real-time, ToS-compliant **Path of Exile 1 Campaign Speedrun & Leveling Companion** built with Python and PyQt6.

Instead of alt-tabbing to read long paragraphs from a walkthrough, this app tails your Path of Exile `Client.txt` log file in real time (`150ms` interval, `0%` GPU/CPU overhead) and automatically displays a **zero-reading visual layout guide** the instant you enter a new zone.

---

## Key Features

* **100% ToS-Compliant Real-Time Zone Detection:**
  * Reads Path of Exile's official `logs/Client.txt` log file (`: You have entered <Zone>.`) — no screen capture, no OCR lag, and no memory reading.
* **Dual-Mode Interface (Switch Anytime with `F9`):**
  1. **Second-Screen Tactical Dashboard ("Mission Control"):** Full companion window for a second monitor showing your current zone's action checklist, speedrunner layout tell, large vector topology schematic, portal/logout reminders, and an interactive Act route timeline.
  2. **In-Game Click-Through HUD Overlay:** Topmost, frameless transparent HUD that floats over Path of Exile (in *Windowed Fullscreen* mode). Uses Windows `WS_EX_TRANSPARENT` (`WindowTransparentForInput`) so your mouse clicks pass straight through into the game.
* **Zero-Paragraph Visual System:**
  * **Compass Badge:** Immediate direction to run (`NE ↗`, `NW ↖`, `LINEAR ↖`, `CLOCKWISE ↻`).
  * **Color-Coded Action Pills:**
    * 🟢 **Emerald (`[MAIN]` / `[EXIT]`):** Main path & zone exits
    * 🟡 **Amber (`[QUEST]` / `[TRIAL]`):** Quest items, Lab Trials & `+1 Passive Skill Point` quests
    * 🔵 **Sky (`[WP]` / `[PORTAL]`):** Waypoints & speedrunner portal/logout tricks
    * 🔴 **Rose (`[BOSS]`):** Required boss fights
  * **Speedrunner "Layout Tell":** 1-line heuristic explaining how to read the zone's random seed generation (e.g., *"The 3 small stones next to The Ledge Waypoint always point toward The Climb exit"*).
  * **Collision-Free Vector Topology Map:** Antialiased live QPainter vector schematic showing `N / S / W / E` compass guides, directional path arrows, and non-overlapping tooltip pills at native widget resolution.
* **Complete Acts 1–10 Campaign Route & Dedicated Labyrinth Trials Tracker:**
  * **Modular Per-Act Route (`data/acts/act1.json` .. `act10.json`):** `103` zone-by-zone steps covering all 10 Acts, all 24 Passive Skill Point quests, and major Pantheon bosses.
  * **Run-Anytime Labyrinth Trials Tracker (`Normal 0/6`, `Cruel 0/3`, `Merciless 0/3`):** Tracks `🔒 Locked` → `🔓 Unlocked — Ready to Run` → `✅ Completed` states across all 12 campaign trials, displaying the exact **Waypoint Hint** and **Trap Type** for any unlocked/skipped trials.
* **Overlay-Only Opacity Slider & Optional Extra Info (Off by Default):**
  * Window mode (`DashboardWindow`) is always locked at **100% opacity** for maximum readability.
  * When **Overlay Mode** is active (`F9`), an **Overlay Opacity Slider (`25%–100%`)** appears in **⚙️ Settings & Opacity** to adjust the In-Game HUD transparency in real time.
  * Optional extra details are hidden by default to keep the UI clean, and can be toggled on anytime inside **⚙️ Settings**:
    * `🛡️ Boss Damage & Resist Warnings`
    * `💎 Quest Gem & Vendor Rewards`
    * `🗺️ Detailed Seed Variations`

---

## Quick Start & Usage Instructions

### 1. Launch the App
* **One-Click Launch (Windows):**
  Double-click **`run_companion.bat`** in the project folder.
* **Command Line Launch:**
  ```powershell
  .\.venv\Scripts\python.exe main.py
  ```

### 2. Using the App While Playing Path of Exile 1
1. **Automatic Sync:** Start the companion app and play Path of Exile normally. Whenever you enter a zone, the Dashboard and Overlay automatically jump to that step in the campaign route.
2. **Using the In-Game Overlay (`F9`):**
   * Make sure Path of Exile's display mode is set to **Windowed Fullscreen** (Borderless Windowed) in-game so overlays can render above it.
   * Press **`F9`** (or click **🖥️ Show In-Game Overlay (F9)** in the top bar) to toggle the in-game HUD.
3. **Repositioning the In-Game Overlay:**
   * Open **⚙️ Settings & Opacity** in the Dashboard.
   * Uncheck **🔒 Lock Overlay Click-Through**.
   * Drag the HUD Overlay anywhere on your screen, then re-check **🔒 Lock Overlay Click-Through** so mouse clicks pass through to PoE again. Your custom position is saved automatically.
4. **Adjusting Opacity & Extra Info:**
   * Click **⚙️ Settings & Opacity** to slide the opacity between `25%` and `100%` or enable optional **Boss Warnings**, **Gem Rewards**, and **Seed Variations**.
5. **Changing Your `Client.txt` Path (If Needed):**
   * The app automatically detects Steam and Standalone PoE installations (defaulting to `C:\Program Files (x86)\Steam\steamapps\common\Path of Exile\logs\Client.txt`).
   * If your game is installed in a custom folder, open **⚙️ Settings & Opacity** and click **📂 Set Client.txt Path...**.

---

## Keyboard Shortcuts

| Shortcut | Action |
| :--- | :--- |
| **`F9`** | Show / Hide the In-Game Click-Through HUD Overlay |
| **`Alt + ]`** | Manually advance to the **Next** campaign step |
| **`Alt + [`** | Manually go back to the **Previous** campaign step |

---

## Project Overview & Architecture

```text
poe1-campaign-companion/
├── AGENTS.md                 # Detailed codebase map & JSON schema guide for AI agents
├── README.md                 # Usage instructions & project overview
├── pyproject.toml            # Project metadata & pytest configuration
├── requirements.txt          # Python dependencies (PyQt6, pytest)
├── main.py                   # Application entry point
├── run_companion.bat         # Windows double-click launcher
├── data/
│   ├── acts/
│   │   └── act1.json .. act10.json # Per-Act declarative steps, layout tells & compass-accurate nodes
│   └── labyrinth_trials.json       # All 12 Campaign Labyrinth Trials (Locked → Unlocked → Completed)
├── src/
│   ├── log_watcher.py        # Non-blocking Client.txt regex parser & incremental tailer
│   ├── route_engine.py       # Stateful campaign step tracker with forward-lookahead matching
│   ├── settings_manager.py   # Persistent user settings (opacity, mode, default-off toggles)
│   └── ui/
│       ├── dashboard_window.py # Second-Screen Tactical Dashboard window
│       ├── overlay_window.py   # Frameless click-through In-Game HUD Overlay
│       └── map_canvas.py       # Custom QPainter vector topology map widget
└── tests/
    └── test_companion.py     # Unit & headless PyQt6 integration tests
```

---

## Running Tests

To run the automated unit and UI integration test suite:

```powershell
.\.venv\Scripts\pytest.exe -v
```
