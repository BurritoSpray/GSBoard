# GSBoard

A free, open-source Linux soundboard that plays sounds through a virtual microphone. No account required. Works in any app that lets you choose a microphone input — games, voice chat, streaming software, etc.

## Features

- Play sounds as if they come from your microphone
- Mix multiple sounds simultaneously
- Configurable per-app routing (e.g. sounds go to Arc Raiders but not Discord)
- Global keyboard shortcuts to trigger sounds
- Macro system — hold a key before/during/after a sound plays
- Drag-and-drop audio file import, folder scanning
- In-app sound recording
- System tray for background operation
- Supports X11 and Wayland

## Requirements

- Linux with PipeWire
- Python 3.10+
- `pactl` and `pw-link` (included with PipeWire)

## Installation

```bash
git clone https://github.com/yourname/GSBoard.git
cd GSBoard
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Running

```bash
.venv/bin/python -m gsboard.main
```

Or install as a command and run with:

```bash
.venv/bin/pip install -e .
.venv/bin/gsboard
```

## How It Works

GSBoard creates a **virtual audio sink** (output device) using PipeWire. Every sound you play is routed to that sink. PipeWire automatically exposes the sink's **monitor** as a microphone source — this is what your other apps select as their mic input.

```
Your sounds → GSBoard virtual sink → Monitor source → Arc Raiders mic input
Your real mic →────────────────────────────────────→ Discord mic input
```

This means you can have sounds audible in one app (Arc Raiders) while your real mic goes to another (Discord), simply by choosing different mic inputs in each app's audio settings.

## Setup Guide

### Step 1 — Create the Virtual Microphone

Open GSBoard and go to the **Settings** tab. At the bottom, under **Virtual Microphone**, click **Create Virtual Mic**. The status should turn green and show:

> Active — select 'gsboard_sink.monitor' as mic in target app

This creates a PipeWire audio device called **GSBoard**. It only needs to be done once per session — GSBoard recreates it automatically on startup.

### Step 2 — Set the Virtual Mic as Input in Your Target App

In the app where you want sounds to be heard (e.g. Arc Raiders):

- Open that app's audio/voice settings
- Find the **microphone input** or **voice input device** option
- Select **"Monitor of GSBoard"** (or **"gsboard_sink.monitor"**)

That app will now receive whatever GSBoard plays, instead of your real microphone.

Any app where you do **not** change the mic input (e.g. Discord) will continue using your real microphone and will not hear your soundboard.

### Step 3 — (Optional) Enable Mic Passthrough

If you want your own voice to also come through the virtual mic — so the target app hears both you and the sounds — enable **mic passthrough**:

1. Under **Audio Routing**, select your real microphone from the **Real Microphone** dropdown
2. Check **Enable mic passthrough**
3. Click **Apply**

This links your real mic into the virtual sink so both your voice and the sounds are mixed together.

### Step 4 — Add Sounds

**Drag and drop** audio files directly onto the Library tab, or:

- Click **+ Add Sound** to pick files from a file browser
- Click **Scan Folder** to import all audio files from your configured sounds folder (set the folder path at the top of Settings)

Supported formats: WAV, FLAC, OGG, MP3, AIFF

Right-click any sound button to rename it, change its color, or adjust its individual volume.

### Step 5 — Set Shortcuts

Go to the **Shortcuts** tab. Click any cell in the **Shortcut** column and press the key combination you want. The shortcut is saved automatically and works globally (even when GSBoard is in the background or minimized to tray).

Example shortcuts: `<ctrl>+<f1>`, `<alt>+b`, `f9`

## Macros

A macro lets you automatically hold down a key while a sound plays. This is useful in games where holding a key activates push-to-talk or a specific action.

In the **Shortcuts** tab, click **Edit Macro** next to a sound:

| Field | Description |
|---|---|
| **Key to hold** | The keyboard key to press (e.g. `b`, `f1`, `v`) |
| **Pre-sound delay** | Milliseconds to wait after pressing the key, before the sound starts |
| **Post-sound delay** | Milliseconds to keep holding the key after the sound finishes |

**Example:** Push-to-talk is bound to `b` in your game. Set key = `b`, pre-delay = `150ms`, post-delay = `100ms`. When you trigger the sound, GSBoard will press `b`, wait 150ms (enough time for the game to register PTT), play the sound, then hold for another 100ms before releasing.

Leave the key field empty to disable the macro for a sound.

## Audio Settings Reference

| Setting | Description |
|---|---|
| **Sound Library Folder** | Directory that **Scan Folder** searches for audio files |
| **Output Device** | Where sounds are sent. Leave as default to use the GSBoard virtual sink. Only change this if you want sounds to go to a different device entirely |
| **Real Microphone** | Your physical mic, used only for passthrough mixing |
| **Mic Passthrough** | Routes your real mic into the virtual sink so your voice is also heard in the target app |
| **Mic Passthrough Volume** | Volume of your voice in the passthrough mix |
| **Master Volume** | Overall volume of all sounds played by GSBoard |

## Supported Audio Formats

GSBoard uses `soundfile` for loading audio. WAV, FLAC, OGG, and AIFF work natively. MP3 support requires `ffmpeg` to be installed on your system:

```bash
# Debian/Ubuntu/Mint
sudo apt install ffmpeg

# Arch/CachyOS
sudo pacman -S ffmpeg
```

## Troubleshooting

**Virtual mic not appearing in target app**
Run `pactl list sources short` in a terminal. You should see `gsboard_sink.monitor`. If not, click **Create Virtual Mic** in the Settings tab and check that PipeWire is running (`systemctl --user status pipewire`).

**No sound playing**
Check that the output device in Settings points to the GSBoard sink, or leave it on default. Verify the virtual mic is active (green status in Settings).

**Global shortcuts not working on Wayland**
Wayland hotkeys require read access to `/dev/input` devices. Add yourself to the `input` group:
```bash
sudo usermod -aG input $USER
# then log out and back in
```

**Sounds are too quiet / too loud**
Use the **Master Volume** slider in Settings, or right-click individual sound buttons to set per-sound volume.
