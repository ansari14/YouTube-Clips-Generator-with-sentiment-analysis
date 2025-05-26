# YouTube Smart Clips Generator

A web application that automatically generates engaging social media clips from YouTube videos by finding the most important and emotionally engaging moments.

## Features

- **Smart Clip Selection**: Uses AssemblyAI's sentiment analysis to identify the most engaging moments in a video
- **Instagram-Ready Format**: Generates clips in 9:16 aspect ratio (1080x1920) perfect for Instagram reels and stories
- **Automatic Subtitles**: Adds subtitles to clips for better engagement on silent playback
- **Easy Download**: Download clips individually with a single click
- **Sentiment Analysis**: Identifies positive segments with high confidence for maximum engagement
- **Fallback System**: Intelligently selects clips based on video structure if sentiment analysis fails

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/youtube-clips-generator.git
   cd youtube-clips-generator
   ```

2. Create a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Install system dependencies:
   - **FFmpeg**: Required for video processing
     - macOS: `brew install ffmpeg`
     - Ubuntu/Debian: `sudo apt install ffmpeg`
     - Windows: Download from [ffmpeg.org](https://ffmpeg.org/download.html)
   - **yt-dlp**: Required for YouTube video downloading
     - Install with: `pip install yt-dlp`

5. Get an AssemblyAI API key:
   - Sign up at [AssemblyAI](https://www.assemblyai.com/) to obtain an API key
   - Replace `YOUR_ASSEMBLYAI_API_KEY` in `podcast_clips.py` with your actual API key

## Usage

1. Start the application:
   ```
   python podcast_clips.py
   ```

2. Open your browser and navigate to:
   ```
   http://localhost:5001
   ```

3. Enter a YouTube URL and click "Generate Smart Clips"

4. The application will:
   - Download the YouTube video
   - Transcribe and analyze the content using AssemblyAI
   - Identify the most engaging sections based on sentiment analysis
   - Create 3 Instagram-ready clips with subtitles
   - Display the clips for playback and download

## How It Works

1. **Video Download**: Using yt-dlp to download the highest quality version of the YouTube video
2. **Audio Extraction & Transcription**: Extracting audio and sending to AssemblyAI for transcription
3. **Sentiment Analysis**: Analyzing the transcript to find segments with positive sentiment and high confidence
4. **Clip Selection**: Choosing the 3 best segments based on sentiment scores
5. **Video Processing**: Creating 9:16 aspect ratio clips with FFmpeg and adding subtitles with MoviePy
6. **Presentation**: Displaying clips with sentiment scores and download options

## Configuration

- Modify clip duration by changing the `clip_duration` variable in `process_video_task()`
- Adjust sentiment threshold by modifying the confidence threshold in `find_engaging_segments()`
- Change output directory by modifying the `CLIPS_DIR` constant

## Troubleshooting

- **Transcription Errors**: Check that your AssemblyAI API key is valid and that you have sufficient credits
- **Video Download Errors**: Ensure yt-dlp is installed and up-to-date
- **Processing Errors**: Make sure FFmpeg is properly installed and accessible in your PATH

## Alternative

If this script seems too complex, you can try [OpusClip](https://www.opus.pro/opusclip), a desktop app that provides similar functionality with a user-friendly interface. 