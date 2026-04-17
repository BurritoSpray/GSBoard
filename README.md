# GSBoard

A free, open-source soundboard for Linux and Windows that plays sounds through a virtual microphone. No account required. Works in any app that lets you choose a microphone input — games, voice chat, streaming software, etc.

## Features

- Play sounds as if they come from your microphone
- Mix multiple sounds simultaneously
- **Dual-channel routing** — separate virtual mics for game and chat apps, mute each independently
- Global keyboard shortcuts to trigger sounds
- **Macro system** — hold a key before/during/after a sound plays (global, per-game, or per-sound)
- **Game detection** — automatically switch macro settings when a game launches (supports native and Wine/Proton games)
- Loopback monitoring — hear your sounds through your headset
- Mic passthrough — mix your real mic into the virtual output so the target app hears both you and the sounds
- Drag-and-drop audio file import, folder scanning
- System tray for background operation
- Supports Windows, X11 and Wayland (KDE Plasma)

## Requirements

### Linux
- PipeWire with `pactl` and `pw-link` (included with PipeWire)
- Python 3.10+ (if running from source)
- **Wayland/KDE:** KGlobalAccel service (ships with KDE Plasma)
- **Shortcut pass-through:** `ydotool` + `ydotoold` (Wayland) or `xdotool` (X11)

### Windows
- Windows 10/11
- [VB-Cable](https://vb-audio.com/Cable/) — free virtual audio cable. GSBoard auto-detects it and routes sound through WASAPI; you just pick "CABLE Output" as the microphone in your target app.
- **Dual-channel routing** (separate mics for game and chat) requires a second cable, e.g. [VB-Cable A+B](https://vb-audio.com/Cable/) (donationware). With a single free cable both channels share it.

## Installation

### Pre-built releases

Download the latest build from the [Releases page](https://github.com/BurritoSpray/GSBoard/releases):

- **Windows:** `GSBoard.exe` — single-file portable executable, just run it
- **Linux:** `GSBoard-*.AppImage` — `chmod +x` and run

### From source

```bash
git clone https://github.com/BurritoSpray/GSBoard.git
cd GSBoard
python3 -m venv .venv
.venv/bin/pip install -e .      # Linux / macOS
.venv\Scripts\pip install -e .  # Windows
```

Platform-specific dependencies (`evdev`, `dbus-python`) are installed automatically only on Linux.

## Running

```bash
.venv/bin/gsboard               # Linux / macOS
.venv\Scripts\gsboard.exe       # Windows
```

## How It Works

**Linux.** GSBoard creates **virtual audio sinks** using PipeWire on startup. Sounds you play are routed through these sinks, which appear as microphone sources in other apps.

```
Your sounds -> GSBoard virtual sink -> Game mic input (e.g. Arc Raiders)
Your real mic -> ----------------------------------------> Chat mic input (e.g. Discord)
```

Pick **"Monitor of GSBoard"** as the mic in the app where you want sounds, and leave your real mic selected everywhere else.

**Windows.** GSBoard auto-detects VB-Cable devices and plays sounds into them via WASAPI. Pick **"CABLE Output"** as the mic in your target app. With a second cable installed, the game and chat channels get separate virtual mics.

## Quick Start

1. **Linux:** the virtual sink is created automatically on first launch. **Windows:** install VB-Cable — it's detected automatically.
2. In your target app's audio settings, pick **"Monitor of GSBoard"** (Linux) or **"CABLE Output"** (Windows) as the microphone.
3. Add sounds via drag-and-drop or **+ Add Sound** in the Library tab.
4. (Optional) Set shortcuts in the **Shortcuts** tab.

## Macros

A macro holds down a key while a sound plays — useful for push-to-talk in games.

| Level | Where to set it |
|---|---|
| **Global** | Shortcuts tab, top section |
| **Per-game** | Games tab, per profile |
| **Per-sound** | Shortcuts tab, "Edit Macro" button next to each sound |

Per-sound macros override per-game macros, which override the global macro.

Each macro has three settings: the **key** to hold, a **pre-delay** (ms before the sound starts), and a **post-delay** (ms to keep holding after the sound ends). Use the **Reset** button in the macro editor to clear all fields.

## Game Detection

The **Games** tab lets you create game profiles that automatically activate a macro when a specific game is running.

- **Process name:** the executable name as seen by the system (e.g. `arc_raider.exe` for a Proton game)
- **Auto-detection:** GSBoard polls running processes and switches macros when a game starts or stops
- **Manual override:** force a specific game profile's macro regardless of what's running
- The active game profile is shown in the status bar

Wine/Proton games are detected by scanning process command lines, so `.exe` names work even though the kernel only sees `wine-preloader`.

## Audio Routing

| Setting | Description |
|---|---|
| **Game mic / Chat mic** | Two independent virtual mic channels, each with a mute toggle and optional shortcut |
| **Loopback** | Mirror sounds to your headset so you can hear what you're playing |
| **Mic Passthrough** | Route your real mic into the virtual sink so the target app hears both you and the sounds |
| **Master Volume** | Overall volume for all sounds |

## Supported Audio Formats

WAV, FLAC, OGG, and AIFF work out of the box. MP3 requires `ffmpeg`:

```bash
# Arch/CachyOS
sudo pacman -S ffmpeg

# Debian/Ubuntu
sudo apt install ffmpeg

# Windows (winget)
winget install Gyan.FFmpeg
```

## Troubleshooting

**(Linux) Virtual mic not appearing** — Run `pactl list sources short` and look for `gsboard_sink.monitor`. If missing, click **Create Virtual Mic** in Settings and check PipeWire is running.

**(Linux) Shortcuts not working on Wayland** — GSBoard uses KGlobalAccel on KDE Plasma. Make sure `dbus-python` is installed and the KGlobalAccel service is running.

**(Linux) Pass-through not working** — Install `ydotool` + enable `ydotoold` (Wayland) or install `xdotool` (X11):
```bash
# Wayland
sudo pacman -S ydotool && systemctl --user enable --now ydotoold

# X11
sudo pacman -S xdotool
```

**(Windows) Target app doesn't hear anything** — Make sure **"CABLE Output"** (not "CABLE Input") is picked as the mic in the target app. "CABLE Input" is GSBoard's output side.

**(Windows) Only one channel works** — The free VB-Cable ships a single device. Install a second cable (e.g. VB-Cable A+B) to use game and chat mics independently.
