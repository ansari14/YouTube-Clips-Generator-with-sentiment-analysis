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

## How It Works

1. User submits a YouTube URL through the web interface
2. The application downloads the video using yt-dlp
3. Audio is extracted and sent to AssemblyAI for transcription and sentiment analysis
4. The most engaging segments are identified based on sentiment scores
5. Clips are created for these segments with proper vertical formatting (9:16 ratio)
6. User can download the generated clips

## Installation

### Prerequisites

- Python 3.8+
- ffmpeg
- yt-dlp
- AssemblyAI API key

### Setup

1. Clone this repository
```bash
git clone https://github.com/yourusername/youtube-clips-generator.git
cd youtube-clips-generator
```

2. Create a virtual environment
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies
```bash
pip install -r requirements.txt
```

4. Set your AssemblyAI API key
```bash
export ASSEMBLYAI_API_KEY="your-api-key-here"
# On Windows: set ASSEMBLYAI_API_KEY=your-api-key-here
```

## Usage

1. Start the application
```bash
python api/index.py
```

2. Open your browser and go to `http://localhost:5001`

3. Enter a YouTube URL and click "Generate Clips"

4. Wait for the processing to complete

5. Download the generated clips

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgements

- [AssemblyAI](https://www.assemblyai.com/) for their excellent transcription and sentiment analysis API
- [Flask](https://flask.palletsprojects.com/) for the web framework
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) for YouTube video downloading
- [ffmpeg](https://ffmpeg.org/) for video processing

## Configuration

You can adjust the following settings in the `api/index.py` file:

- `FAST_MODE`: Set to `True` for faster processing (lower quality) or `False` for higher quality
- `MAX_VIDEO_DURATION`: Maximum duration of the input video to process (in seconds, currently set to 7200 seconds / 2 hours)
- `MAX_CLIP_DURATION`: Duration of the generated clips (in seconds)
- `MAX_CLIPS`: Maximum number of clips to generate

## Project Structure

```
├── api/
│   └── index.py          # Main Flask application
├── static/
│   └── css/
│       └── style.css     # CSS styles for the web interface
├── templates/
│   ├── index.html        # Home page template
│   └── status.html       # Processing status page template
├── clips_output/         # Directory for generated clips
├── temp/                 # Directory for temporary files
├── requirements.txt      # Python dependencies
└── README.md             # This file
``` 