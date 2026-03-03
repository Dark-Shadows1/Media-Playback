# Media-Playback

Simple portable-style Windows video playback controller.

## What this app does

- Shows a **controller window** with:
  - Top toolbar controls (Play, Pause, Reverse -10s, Forward +10s)
  - Monitor selector for where fullscreen playback should appear
  - Bottom half gallery list of videos with thumbnail previews
- Clicking a video loads it in the playback display and opens it **fullscreen on the selected monitor**, initially **paused**.

## Quick start (development)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

1. Click **Open Folder** and choose a directory with videos (`.mp4`, `.mkv`, `.avi`, `.mov`, `.wmv`, `.m4v`, `.webm`).
2. Pick the target monitor from **Playback Monitor**.
3. Click a video thumbnail to load it fullscreen and paused.
4. Use toolbar controls to play/pause/seek.

## Thumbnail previews

- If `ffmpeg` is on `PATH`, the app extracts a frame preview around 2 seconds into each video.
- If `ffmpeg` is not available, a placeholder image is shown.

## Build a portable Windows executable

Install PyInstaller:

```bash
pip install pyinstaller
```

Build:

```bash
pyinstaller --noconfirm --windowed --name MediaPlaybackController app.py
```

Portable output folder:

- `dist/MediaPlaybackController/`

Copy this whole folder to another Windows machine and run `MediaPlaybackController.exe`.

> Note: If target machines do not already have codecs/ffmpeg, previews may fall back to placeholders depending on the video format.
