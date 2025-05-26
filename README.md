# YouTube Clips Generator

A Flask web application that automatically generates engaging Instagram-ready clips from YouTube videos using sentiment analysis.

**Created entirely using Cursor AI without writing a single line of code!**

## Features

- Automatically identifies the most engaging moments in YouTube videos
- Creates vertical clips with 9:16 aspect ratio (1080x1920) for Instagram
- Adds subtitles to increase engagement
- Optimized processing for faster clip generation
- Web interface to submit YouTube URLs and download clips

## About This Project

This project demonstrates the power of AI-assisted development. The entire application was built by providing instructions to Cursor AI, which generated all the code, making it possible to create a complex application without writing a single line of code manually.

## Installation

1. Clone this repository:
```bash
git clone https://github.com/ansari14/YouTube-Clips-Generator-with-sentiment-analysis.git
cd YouTube-Clips-Generator-with-sentiment-analysis
```

2. Create and activate a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install the dependencies:
```bash
pip install -r requirements.txt
```

4. Make sure you have ffmpeg installed on your system:
   - On Mac: `brew install ffmpeg`
   - On Ubuntu/Debian: `sudo apt-get install ffmpeg`
   - On Windows: Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to PATH

5. Get an AssemblyAI API key from [assemblyai.com](https://www.assemblyai.com/) and update it in the `podcast_clips.py` file.

## Usage

1. Run the application:
```bash
python podcast_clips.py
```

2. Open your browser and go to `http://localhost:5001`

3. Enter a YouTube URL and click "Generate Clips"

4. Wait for the processing to complete (this may take some time depending on the video length)

5. Download the generated clips

## Configuration

You can adjust the following settings in the `podcast_clips.py` file:

- `FAST_MODE`: Set to `True` for faster processing (lower quality) or `False` for higher quality
- `MAX_VIDEO_DURATION`: Maximum duration of the input video to process (in seconds)
- `MAX_CLIP_DURATION`: Duration of the generated clips (in seconds)
- `MAX_CLIPS`: Maximum number of clips to generate

## License

MIT 