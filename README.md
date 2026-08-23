# AI Metatagger 🎬🤖

**AI Metatagger** is an intelligent, automated assistant and validation cockpit designed to clean up, analyze, and correctly tag audio and subtitle tracks in your MKV media library (e.g., for Jellyfin, Emby, or Plex). 

Manually tagging languages, finding "SDH" (Deaf or Hard-of-Hearing) markers, and isolating "Forced" subtitles in large media collections is a tedious process. This project solves that by using AI to analyze the tracks automatically, combined with a powerful GUI to quickly validate and save the results.

## Features ✨
- **AI-Powered Analysis:** Automatically parses your .mkv files and predicts the correct language (ISO code), whether a subtitle is SDH, and if it is a Forced track.
- **Validation Cockpit (GUI):** A PyQt5-based user interface that lets you easily review the AI's predictions side-by-side with your own manual corrections.
- **Field-by-Field Validation:** Validate individual fields (Language, SDH, Forced, Special Name) with instant visual feedback.
- **Embedded VLC Player:** Instantly jump to predefined timestamps in the video to visually test the subtitles and hear the audio before confirming.
- **Track List Navigation:** Easily switch between different tracks of a selected movie with a dedicated track-list sidebar.
- **State Persistence:** Automatically saves your progress to an Excel matrix and a local JSON state file.
- **Auto-Tagging:** Saves the confirmed metadata directly back into the .mkv file using mkvpropedit.

## Prerequisites 🛠️
- **Python 3.x**
- **VLC Media Player** (must be installed on the system)
- **MKVToolNix** (specifically mkvpropedit)
- **FFmpeg / FFprobe**

## Installation 🚀
1. Clone the repository:
   `ash
   git clone https://github.com/Haptic99/AI_Metatager.git
   `
2. Install the required Python packages:
   `ash
   pip install PyQt5 pandas python-vlc openpyxl
   `
3. Update the directory paths in Cockpit_V2.py (e.g., DIR_FILME, MKVPROPEDIT) to match your local environment.

## Usage 🎯
Run the cockpit interface via the provided batch script or directly:
`ash
python Cockpit_V2.py
`