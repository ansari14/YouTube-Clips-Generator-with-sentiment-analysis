# YouTube Clips Generator

A Flask web application that automatically generates engaging Instagram-ready clips from YouTube videos using sentiment analysis.

**Created entirely using Cursor AI without writing a single line of code!**

## Features

- Automatically identifies the most engaging moments in YouTube videos
- Creates vertical clips with 9:16 aspect ratio (1080x1920) for Instagram
- Adds subtitles to increase engagement
- Optimized processing for faster clip generation
- Web interface to submit YouTube URLs and download clips
- Deployable to Vercel as a serverless application

## About This Project

This project demonstrates the power of AI-assisted development. The entire application was built by providing instructions to Cursor AI, which generated all the code, making it possible to create a complex application without writing a single line of code manually.

## Local Installation

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

5. Get an AssemblyAI API key from [assemblyai.com](https://www.assemblyai.com/) and set it as an environment variable:
```bash
export ASSEMBLYAI_API_KEY="your_api_key_here"
```

## Local Usage

1. Run the application:
```bash
python api/index.py
```

2. Open your browser and go to `http://localhost:5001`

3. Enter a YouTube URL and click "Generate Smart Clips"

4. Wait for the processing to complete (this may take some time depending on the video length)

5. Download the generated clips

## Vercel Deployment

This project is ready to be deployed to Vercel as a serverless application. Follow these steps:

1. Fork or push this repository to your GitHub account

2. Sign up for a Vercel account at [vercel.com](https://vercel.com) if you don't have one

3. Connect your GitHub account to Vercel

4. Create a new project in Vercel and select your repository

5. Configure the environment variables:
   - Add `ASSEMBLYAI_API_KEY` with your AssemblyAI API key

6. Deploy the project

7. Once deployed, your application will be available at `https://your-project-name.vercel.app`

### Important Notes for Vercel Deployment

- Vercel has limitations for serverless functions:
  - 10-second execution timeout for free tier (may not be enough for processing long videos)
  - 50MB maximum deployment size
  - Limited storage (clips are not permanently stored)

- For production use, consider:
  - Upgrading to a paid Vercel plan
  - Using cloud storage like AWS S3 for storing clips
  - Implementing a queue system for processing longer videos

## Configuration

You can adjust the following settings in the `api/index.py` file:

- `FAST_MODE`: Set to `True` for faster processing (lower quality) or `False` for higher quality
- `MAX_VIDEO_DURATION`: Maximum duration of the input video to process (in seconds)
- `MAX_CLIP_DURATION`: Duration of the generated clips (in seconds)
- `MAX_CLIPS`: Maximum number of clips to generate

## Project Structure

```
├── api/
│   └── index.py          # Main Flask application for Vercel
├── static/
│   └── css/
│       └── style.css     # CSS styles for the web interface
├── templates/
│   ├── index.html        # Home page template
│   └── status.html       # Processing status page template
├── clips_output/         # Directory for generated clips
├── temp/                 # Directory for temporary files
├── requirements.txt      # Python dependencies
├── vercel.json           # Vercel configuration
└── README.md             # This file
```

## License

MIT 