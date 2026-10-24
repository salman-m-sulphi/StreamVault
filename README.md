# StreamVault

A Windows desktop application for downloading media you are authorized to save, with tools for keeping yt-dlp and FFmpeg updated.

## Credits

- **Version 1: Nikhil Joji** — original StreamVault application.
- **Updated version / Version 2: Salman M Sulphi** — created with assistance from GPT (OpenAI), building on the original application's concept and workflow.

This repository contains the updated Python implementation. It does not contain the original Version 1 source code.

## Features

- Analyze video and livestream links and choose a download format.
- Download media with yt-dlp and FFmpeg.
- Update yt-dlp and FFmpeg from the application's local tools controls.
- Verify online update checksums, retain previous binaries, and replace local tool files.
- Optional authorized YouTube channel monitoring and automatic backups of completed broadcasts while the app is open.
- Encrypt the YouTube refresh token for the current Windows user with Windows Data Protection API.

## Run from source

Requires Windows and Python 3.10 or newer with Tkinter installed. The application uses Python's standard library; media processing uses separate yt-dlp and FFmpeg executables.

```powershell
python streamvault.py
```

On first launch, available tools are copied from the original StreamVault tools folder. Use **Update yt-dlp** and **Update FFmpeg** to install or update the isolated tools. Application data is stored under `%LOCALAPPDATA%\StreamVault-Rebuilt`.

See [AUTO_BACKUP_SETUP.md](AUTO_BACKUP_SETUP.md) for optional YouTube authorization and backup setup. Keep OAuth client files, tokens, settings, cookies, downloaded media, and application data out of the repository.

## Build a Windows executable

```powershell
python -m pip install pyinstaller==6.22.3
python -m PyInstaller --noconfirm --onefile --windowed --name StreamVault-v2 streamvault.py
```

The resulting executable is written to `dist/StreamVault-v2.exe`.

## Validation and limitations

The initial rebuild passed local media analysis/download checks and simulated checksum and tool-installation failure checks. The later YouTube authorization and automatic-backup features have not been verified against a live YouTube account. This is a desktop application; the proposed server architecture and SimHub integration are not implemented here.

## External projects

- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [FFmpeg](https://ffmpeg.org/) and [Gyan Windows builds](https://www.gyan.dev/ffmpeg/builds/)
- [Python](https://www.python.org/) and [PyInstaller](https://pyinstaller.org/)

External components retain their respective licenses. No license for Nikhil Joji's original application is asserted by this repository.
