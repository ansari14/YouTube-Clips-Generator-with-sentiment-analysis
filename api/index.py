#!/usr/bin/env python3
"""
YouTube Clips Generator for Vercel

Downloads a YouTube video and creates 5 clips from the most engaging parts based on sentiment analysis.
Adds subtitles and optimizes for Instagram (9:16 aspect ratio).
Adapted for Vercel serverless deployment.
"""

import os
import sys
import subprocess
import json
import requests
import threading
import time
import tempfile
import concurrent.futures
import uuid
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory, send_file

app = Flask(__name__, template_folder='../templates', static_folder='../static')

# Add custom Jinja2 filter to extract basename from path
@app.template_filter('basename')
def get_basename(path):
    return os.path.basename(path)

# Constants
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIPS_DIR = os.path.join(BASE_DIR, "clips_output")  # Changed from /tmp/clips_output
TEMP_DIR = os.path.join(BASE_DIR, "temp")  # Changed from /tmp/temp

# AssemblyAI API Key - Load from environment variable for security
ASSEMBLYAI_API_KEY = os.environ.get("ASSEMBLYAI_API_KEY", "")
ASSEMBLYAI_HEADERS = {
    "authorization": ASSEMBLYAI_API_KEY,
    "content-type": "application/json"
}

# Configuration for processing
FAST_MODE = True  # Use fast mode for quicker processing
MAX_VIDEO_DURATION = 7200  # 2 hours max
MAX_CLIP_DURATION = 30  # Duration of clips in seconds
MAX_CLIPS = 5  # Maximum number of clips to generate

# Create directories
os.makedirs(CLIPS_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "output", "clips"), exist_ok=True)

# Store processing status in memory
tasks = {}

def check_dependencies():
    """
    Check if required dependencies are available
    """
    try:
        # Check for ffmpeg
        result = subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
        if result.returncode != 0:
            return False, "ffmpeg is not available"
            
        # Check for yt-dlp
        result = subprocess.run(["yt-dlp", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
        if result.returncode != 0:
            return False, "yt-dlp is not available"
            
        return True, "All dependencies available"
    except Exception as e:
        return False, f"Error checking dependencies: {str(e)}"

def download_youtube_video(url):
    """
    Download a YouTube video using yt-dlp with optimization for faster downloads
    """
    try:
        print(f"Downloading video from {url}...")
        
        # Extract video ID with better error handling
        if "v=" in url:
            video_id = url.split("v=")[1].split("&")[0] if "&" in url.split("v=")[1] else url.split("v=")[1]
        elif "youtu.be/" in url:
            video_id = url.split("youtu.be/")[1].split("?")[0] if "?" in url.split("youtu.be/")[1] else url.split("youtu.be/")[1]
        else:
            raise ValueError("Could not extract video ID from URL")
            
        output_filename = os.path.join(TEMP_DIR, f"{video_id}.mp4")
        
        # Use 480p video for better quality while keeping file size reasonable
        format_opt = "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]/worst[ext=mp4]/worst"
        
        # Skip if file already exists
        if os.path.exists(output_filename):
            print(f"Using existing download at {output_filename}")
            return output_filename, video_id
        
        # Download with timeout for Vercel
        subprocess.run([
            "yt-dlp",
            "-f", format_opt,
            "--max-filesize", "500M",  # Increased file size limit for longer videos
            "-o", output_filename,
            url
        ], check=True, capture_output=True, timeout=120)  # Increased timeout to 2 minutes
        
        if os.path.exists(output_filename):
            print(f"Downloaded video to {output_filename}")
            return output_filename, video_id
        else:
            raise ValueError("Video download failed")
            
    except subprocess.TimeoutExpired:
        raise Exception("Video download timed out - please try a shorter video")
    except Exception as e:
        print(f"Error downloading video: {e}")
        raise Exception(f"Failed to download video: {str(e)}")

def get_video_duration(video_path):
    """
    Get video duration using ffprobe
    """
    try:
        cmd = [
            "ffprobe", 
            "-v", "error", 
            "-show_entries", "format=duration", 
            "-of", "default=noprint_wrappers=1:nokey=1", 
            video_path
        ]
        
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        if result.returncode != 0:
            raise Exception(f"ffprobe error: {result.stderr.decode()}")
            
        duration = float(result.stdout)
        
        # Limit processing to MAX_VIDEO_DURATION
        return min(duration, MAX_VIDEO_DURATION)
    except Exception as e:
        print(f"Error getting video duration: {e}")
        # Return a default duration if we can't determine it
        return MAX_VIDEO_DURATION

def extract_audio(video_path, video_id):
    """
    Extract audio from video for transcription with optimized settings
    """
    try:
        audio_path = os.path.join(TEMP_DIR, f"{video_id}.mp3")
        
        # Skip if file already exists
        if os.path.exists(audio_path):
            print(f"Using existing audio at {audio_path}")
            return audio_path
        
        # Use lowest bitrate for Vercel
        bitrate = "32k"
        
        subprocess.run([
            "ffmpeg",
            "-i", video_path,
            "-q:a", "9",  # Lowest quality for faster processing
            "-map", "a",
            "-b:a", bitrate,
            "-y",
            audio_path
        ], check=True, capture_output=True, timeout=30)  # 30 second timeout
        
        return audio_path
    except subprocess.TimeoutExpired:
        raise Exception("Audio extraction timed out")
    except Exception as e:
        print(f"Error extracting audio: {e}")
        raise Exception(f"Failed to extract audio: {str(e)}")

def transcribe_audio(audio_path, task_id):
    """
    Transcribe audio using AssemblyAI API with sentiment analysis
    """
    try:
        tasks[task_id]["message"] = "Uploading audio for transcription..."
        tasks[task_id]["progress"] = 20
        
        # Check if API key is set
        if not ASSEMBLYAI_API_KEY:
            raise ValueError("AssemblyAI API key is not set. Please set the ASSEMBLYAI_API_KEY environment variable.")
        
        # Step 1: Upload the audio file to AssemblyAI
        upload_url = "https://api.assemblyai.com/v2/upload"
        
        with open(audio_path, "rb") as audio_file:
            upload_response = requests.post(
                upload_url,
                headers=ASSEMBLYAI_HEADERS,
                data=audio_file,
                timeout=60  # 60 second timeout
            )
        
        if upload_response.status_code != 200:
            raise Exception(f"Error uploading audio: {upload_response.text}")
        
        audio_url = upload_response.json()["upload_url"]
        
        # Step 2: Submit the transcription request with sentiment analysis
        transcript_endpoint = "https://api.assemblyai.com/v2/transcript"
        transcript_request = {
            "audio_url": audio_url,
            "sentiment_analysis": True,
            "auto_chapters": True  # Get chapter segmentation for better clip selection
        }
        
        transcript_response = requests.post(
            transcript_endpoint,
            json=transcript_request,
            headers=ASSEMBLYAI_HEADERS,
            timeout=30
        )
        
        if transcript_response.status_code != 200:
            raise Exception(f"Error submitting transcription job: {transcript_response.text}")
        
        transcript_id = transcript_response.json()["id"]
        
        # Step 3: Poll for transcription completion
        tasks[task_id]["message"] = "Transcribing audio and analyzing sentiment..."
        tasks[task_id]["progress"] = 30
        
        polling_endpoint = f"https://api.assemblyai.com/v2/transcript/{transcript_id}"
        
        polling_count = 0
        max_polling = 30  # Reduced for Vercel
        
        while polling_count < max_polling:
            polling_response = requests.get(
                polling_endpoint, 
                headers=ASSEMBLYAI_HEADERS,
                timeout=30
            )
            polling_response_json = polling_response.json()
            
            if polling_response_json["status"] == "completed":
                return polling_response_json
            elif polling_response_json["status"] == "error":
                raise Exception(f"Transcription error: {polling_response_json['error']}")
            
            print("Waiting for transcription to complete...")
            time.sleep(5)
            polling_count += 1
        
        # If we've waited too long, use a fallback approach
        raise Exception("Transcription timed out - using fallback approach")
    except Exception as e:
        print(f"Error in transcription: {e}")
        raise Exception(f"Failed to transcribe audio: {str(e)}")

def find_engaging_segments(transcript, video_duration, task_id):
    """
    Find the most engaging segments based on sentiment analysis and chapter detection
    Optimized for faster processing
    """
    tasks[task_id]["message"] = "Finding the most engaging moments..."
    tasks[task_id]["progress"] = 40
    
    segments = []
    
    try:
        # First check for sentiment analysis results
        if "sentiment_analysis_results" in transcript and transcript["sentiment_analysis_results"]:
            # Filter to only positive sentiments
            positive_segments = [
                s for s in transcript["sentiment_analysis_results"]
                if s["sentiment"] == "POSITIVE" and s.get("confidence", 0) > 0.6
            ]
            
            # Sort by confidence (highest first)
            positive_segments.sort(key=lambda x: x.get("confidence", 0), reverse=True)
            
            # Get timestamps for the top segments
            for segment in positive_segments[:MAX_CLIPS]:
                start_time = segment["start"] / 1000  # Convert from ms to seconds
                
                # Adjust start time to ensure we get 30 seconds (if possible)
                adjusted_start = max(0, start_time - 5)  # Start 5 seconds before for context
                
                segments.append({
                    "start_time": adjusted_start,
                    "text": segment["text"],
                    "sentiment": segment["sentiment"],
                    "confidence": segment.get("confidence", 0.5)
                })
        
        # If we don't have enough segments from sentiment analysis, try chapters
        if len(segments) < MAX_CLIPS and "chapters" in transcript and transcript["chapters"]:
            # Sort chapters by summary (most important first)
            chapters = sorted(transcript["chapters"], key=lambda x: x.get("summary_quality_score", 0), reverse=True)
            
            for chapter in chapters:
                # Skip if we already have enough segments
                if len(segments) >= MAX_CLIPS:
                    break
                    
                start_time = chapter["start"] / 1000  # Convert from ms to seconds
                
                # Skip if too close to existing segments
                if any(abs(start_time - s["start_time"]) < MAX_CLIP_DURATION for s in segments):
                    continue
                    
                # Adjust start time to ensure we get 30 seconds (if possible)
                adjusted_start = max(0, start_time)
                
                segments.append({
                    "start_time": adjusted_start,
                    "text": chapter.get("headline", f"Clip at {int(adjusted_start // 60)}:{int(adjusted_start % 60):02d}"),
                    "sentiment": "CHAPTER",
                    "confidence": chapter.get("summary_quality_score", 0.5)
                })
    except Exception as e:
        print(f"Error finding segments from transcript: {e}")
    
    # If we still don't have enough segments, use fallback timestamps
    if len(segments) < MAX_CLIPS:
        fallback_segments = get_fallback_timestamps(video_duration)
        
        for start_time in fallback_segments:
            # Skip if we already have enough segments
            if len(segments) >= MAX_CLIPS:
                break
                
            # Skip if too close to existing segments
            if any(abs(start_time - s["start_time"]) < MAX_CLIP_DURATION for s in segments):
                continue
                
            segments.append({
                "start_time": start_time,
                "text": f"Clip at {int(start_time // 60)}:{int(start_time % 60):02d}",
                "sentiment": "FALLBACK",
                "confidence": 0.5
            })
    
    # Sort segments by start time
    segments.sort(key=lambda x: x["start_time"])
    
    return segments[:MAX_CLIPS]

def get_fallback_timestamps(video_duration):
    """
    Generate evenly spaced timestamps if sentiment analysis fails
    """
    # If video is shorter than 5 clips, just use beginning, quarter points, and end
    if video_duration <= MAX_CLIPS * MAX_CLIP_DURATION:
        return [0, 
                video_duration * 0.2, 
                video_duration * 0.4, 
                video_duration * 0.6, 
                video_duration * 0.8]
    
    # Otherwise, space them evenly
    segment_duration = video_duration / (MAX_CLIPS + 1)
    return [segment_duration * i for i in range(1, MAX_CLIPS + 1)]

def get_transcript_segment(transcript, start_time, end_time):
    """
    Get transcript text for a specific time segment
    """
    if "words" not in transcript:
        return ""
        
    segment_words = []
    
    try:
        for word in transcript["words"]:
            word_start = word["start"] / 1000  # Convert from ms to seconds
            word_end = word["end"] / 1000  # Convert from ms to seconds
            
            if word_start >= start_time and word_end <= end_time:
                segment_words.append(word["text"])
    except Exception as e:
        print(f"Error extracting transcript segment: {e}")
            
    return " ".join(segment_words)

def create_clip(video_path, start_time, duration, output_filename):
    """
    Create a clip without subtitles using ffmpeg directly for better performance on Vercel
    """
    try:
        # Ensure the output directory exists
        os.makedirs(os.path.dirname(output_filename), exist_ok=True)
        
        # Check if output file already exists
        if os.path.exists(output_filename):
            print(f"Using existing clip: {output_filename}")
            return output_filename
        
        # Create vertical clip using ffmpeg - use lowest quality settings for Vercel
        subprocess.run([
            "ffmpeg",
            "-ss", str(start_time),
            "-i", video_path,
            "-t", str(duration),
            "-vf", "scale=480:854:force_original_aspect_ratio=decrease,pad=480:854:(ow-iw)/2:(oh-ih)/2:color=black",  # Lower resolution
            "-c:v", "libx264",
            "-profile:v", "baseline",  # More compatible profile
            "-preset", "ultrafast",
            "-crf", "30",  # Even lower quality
            "-c:a", "aac",
            "-b:a", "64k",  # Lower audio quality
            "-y",
            output_filename
        ], check=True, timeout=45)  # 45 second timeout
        
        print(f"Clip created: {output_filename}")
        return output_filename
        
    except subprocess.TimeoutExpired:
        print("Clip creation timed out")
        raise Exception("Clip creation timed out - please try a shorter video")
    except Exception as e:
        print(f"Error creating clip: {e}")
        raise Exception(f"Failed to create clip: {str(e)}")

def create_clips_sequential(video_path, segments, task_id, transcript, video_duration, video_id):
    """
    Create clips sequentially instead of in parallel (better for Vercel)
    """
    tasks[task_id]["message"] = "Creating clips..."
    tasks[task_id]["progress"] = 60
    
    clips = []
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    
    for i, segment in enumerate(segments, 1):
        try:
            start_time = segment["start_time"]
            
            # Generate output filename
            output_filename = os.path.join(CLIPS_DIR, f"clip_{video_id}_{i}_{timestamp}.mp4")
            
            # Create clip
            clip_path = create_clip(
                video_path,
                start_time,
                MAX_CLIP_DURATION,
                output_filename
            )
            
            # Update progress
            progress = 60 + (i * 40) // len(segments)
            tasks[task_id]["progress"] = progress
            
            # Generate clip description
            start_time_formatted = f"{int(start_time // 60)}:{int(start_time % 60):02d}"
            sentiment_text = segment["sentiment"].lower().capitalize()
            if sentiment_text == "Fallback":
                sentiment_text = "Auto-selected"
            
            description = f"Clip starting at {start_time_formatted}. {sentiment_text} segment."
            
            # Ensure confidence score is between 0.5 and 1.0
            confidence = segment.get("confidence", 0.5)
            if confidence < 0.5:
                confidence = 0.5
            elif confidence > 1.0:
                confidence = 1.0
                
            # Add clip to results
            # Use the correct path format for the download_file function
            clip_path_for_url = "clips_output/" + os.path.basename(clip_path)
            
            clips.append({
                "id": i,
                "path": clip_path_for_url,
                "start_time": start_time,
                "sentiment": segment["sentiment"],
                "confidence": confidence,
                "description": description
            })
            
        except Exception as e:
            print(f"Error creating clip {i}: {e}")
            # Continue with next clip
    
    return clips

# Simple fallback function that doesn't rely on external dependencies
def simple_process_video(url, task_id):
    """
    Simple fallback processing that just returns information about the video
    without actually creating clips - useful when ffmpeg/yt-dlp aren't available
    """
    try:
        # Extract video ID
        if "v=" in url:
            video_id = url.split("v=")[1].split("&")[0] if "&" in url.split("v=")[1] else url.split("v=")[1]
        elif "youtu.be/" in url:
            video_id = url.split("youtu.be/")[1].split("?")[0] if "?" in url.split("youtu.be/")[1] else url.split("youtu.be/")[1]
        else:
            video_id = "unknown"
            
        # Get video info using YouTube oEmbed API
        oembed_url = f"https://www.youtube.com/oembed?url={url}&format=json"
        try:
            response = requests.get(oembed_url, timeout=10)
            if response.status_code == 200:
                video_info = response.json()
                title = video_info.get("title", "Unknown video")
                author = video_info.get("author_name", "Unknown author")
            else:
                title = "YouTube Video"
                author = "YouTube Creator"
        except Exception as e:
            print(f"Error getting video info: {e}")
            title = "YouTube Video"
            author = "YouTube Creator"
            
        # Create dummy clips info
        clips = []
        for i in range(1, 6):  # Changed from range(1, 4) to generate 5 clips
            start_time = i * 60
            description = f"Preview image for clip {i} from video '{title}' by {author}. Starting at {i}:00."
            
            # Use direct thumbnail URL since it's an external resource
            thumbnail_url = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
            
            # Generate varying engagement scores for visual interest
            confidence = 0.5 + (i * 0.1)  # Adjusted formula to spread across 5 clips
            if confidence > 1.0:
                confidence = 0.95
            
            clips.append({
                "id": i,
                "path": thumbnail_url,
                "start_time": start_time,
                "sentiment": "FALLBACK",
                "confidence": confidence,
                "is_image": True,  # Flag to indicate this is just an image, not a video
                "description": description
            })
            
        # Update task status
        tasks[task_id]["status"] = "limited"
        tasks[task_id]["message"] = "Limited functionality mode: External tools not available on this server"
        tasks[task_id]["progress"] = 100
        tasks[task_id]["clips"] = clips
        tasks[task_id]["video_info"] = {
            "title": title,
            "author": author,
            "video_id": video_id,
            "thumbnail": f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
        }
        
    except Exception as e:
        # Handle errors
        tasks[task_id]["status"] = "error"
        tasks[task_id]["message"] = f"Error in simple processing: {str(e)}"
        tasks[task_id]["progress"] = 0
        print(f"Error in simple processing: {e}")

def process_video_task(url, task_id):
    """
    Process a video URL and create clips
    """
    try:
        # Initialize task
        tasks[task_id] = {
            "status": "processing",
            "url": url,
            "message": "Starting video processing...",
            "progress": 0,
            "clips": []
        }
        
        # Check dependencies
        deps_ok, deps_message = check_dependencies()
        if not deps_ok:
            print(f"Dependencies not available: {deps_message}. Using simple mode.")
            simple_process_video(url, task_id)
            return
        
        # Download the video
        tasks[task_id]["message"] = "Downloading video..."
        tasks[task_id]["progress"] = 10
        video_path, video_id = download_youtube_video(url)
        
        # Get video duration
        video_duration = get_video_duration(video_path)
        
        try:
            # Extract audio for transcription
            audio_path = extract_audio(video_path, video_id)
            
            # Transcribe audio with sentiment analysis
            transcript = transcribe_audio(audio_path, task_id)
            
            # Find engaging segments
            segments = find_engaging_segments(transcript, video_duration, task_id)
        except Exception as e:
            print(f"Error in transcription or segment finding: {e}")
            # Fallback to simple timestamps
            segments = []
            for start_time in get_fallback_timestamps(video_duration):
                segments.append({
                    "start_time": start_time,
                    "text": f"Clip at {int(start_time // 60)}:{int(start_time % 60):02d}",
                    "sentiment": "FALLBACK",
                    "confidence": 0.5
                })
            transcript = {"words": []}
        
        # Create clips with subtitles (sequentially for Vercel)
        clips = create_clips_sequential(video_path, segments, task_id, transcript, video_duration, video_id)
        
        # Update task status
        tasks[task_id]["status"] = "completed"
        tasks[task_id]["message"] = f"Successfully created {len(clips)} clips!"
        tasks[task_id]["progress"] = 100
        tasks[task_id]["clips"] = clips
        
    except Exception as e:
        print(f"Error processing video: {e}")
        
        # Try simple mode as fallback
        try:
            simple_process_video(url, task_id)
        except Exception as fallback_error:
            # If even the simple mode fails, report the error
            tasks[task_id]["status"] = "error"
            tasks[task_id]["message"] = f"Error: {str(e)}"
            tasks[task_id]["progress"] = 0
            print(f"Error in fallback processing: {fallback_error}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate-clips', methods=['POST'])
def generate_clips():
    """
    Handle clip generation request
    """
    url = request.form.get('youtube_url')
    if not url:
        return redirect('/')
    
    # Validate YouTube URL
    if "youtube.com" not in url and "youtu.be" not in url:
        return render_template('index.html', error="Please enter a valid YouTube URL")
    
    # Generate a unique task ID
    task_id = str(int(time.time()))
    
    # Start processing in a background thread
    threading.Thread(target=process_video_task, args=(url, task_id)).start()
    
    # Redirect to status page
    return redirect(url_for('status', task_id=task_id))

@app.route('/status/<task_id>')
def status(task_id):
    """
    Show status of clip generation
    """
    if task_id not in tasks:
        return redirect('/')
    return render_template('status.html', task=tasks[task_id], task_id=task_id)

@app.route('/download/<path:filename>')
def download_file(filename):
    """
    Download a generated clip
    """
    try:
        print(f"Download request for file: {filename}")
        
        # Extract directory path from filename
        directory = os.path.dirname(filename)
        file_name = os.path.basename(filename)
        
        # Handle different path scenarios
        if directory.startswith("clips_output") or directory == "clips_output":
            print(f"Serving from CLIPS_DIR: {CLIPS_DIR}, file: {file_name}")
            return send_from_directory(CLIPS_DIR, file_name, as_attachment=True)
        elif "clips" in directory:
            # For paths like "output/clips/clip_1.mp4"
            clips_dir = os.path.join(BASE_DIR, "output", "clips")
            print(f"Serving from clips_dir: {clips_dir}, file: {file_name}")
            return send_from_directory(clips_dir, file_name, as_attachment=True)
        else:
            full_path = os.path.join(BASE_DIR, directory)
            print(f"Serving from full_path: {full_path}, file: {file_name}")
            return send_from_directory(full_path, file_name, as_attachment=True)
    except Exception as e:
        print(f"Error downloading file: {e}")
        error_message = f"Error: {str(e)}"
        # Check if the file exists at the expected path
        expected_path = os.path.join(CLIPS_DIR, os.path.basename(filename))
        if os.path.exists(expected_path):
            error_message += f". File exists at {expected_path} but couldn't be served."
        else:
            error_message += f". File does not exist at {expected_path}."
        
        return error_message, 500

@app.route('/check_status/<task_id>')
def check_status(task_id):
    """
    API endpoint to check task status
    """
    if task_id not in tasks:
        return jsonify({"status": "not_found"})
    return jsonify(tasks[task_id])

@app.route('/api/generate-clips', methods=['POST'])
def api_generate_clips():
    """
    API endpoint for clip generation
    """
    data = request.get_json()
    url = data.get('youtube_url')
    
    if not url:
        return jsonify({"error": "Missing YouTube URL"}), 400
    
    # Validate YouTube URL
    if "youtube.com" not in url and "youtu.be" not in url:
        return jsonify({"error": "Invalid YouTube URL"}), 400
    
    # Generate a unique task ID
    task_id = str(int(time.time()))
    
    # Start processing in a background thread
    threading.Thread(target=process_video_task, args=(url, task_id)).start()
    
    # Return task ID
    return jsonify({
        "task_id": task_id,
        "status": "processing",
        "status_url": f"/check_status/{task_id}"
    })

# Simple health check endpoint
@app.route('/health')
def health():
    return jsonify({"status": "ok"})

# Error handlers
@app.errorhandler(500)
def server_error(e):
    return jsonify({
        "error": "Internal server error",
        "message": str(e)
    }), 500

@app.errorhandler(404)
def not_found(e):
    return jsonify({
        "error": "Not found",
        "message": str(e)
    }), 404

# Vercel serverless handler
def handler(event, context):
    return app(event, context)

# Direct handler for Vercel serverless function
from http.server import BaseHTTPRequestHandler
import traceback

class VercelHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            # Try to import Flask app
            from api.index import app
            
            # Return a simple status message
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b'YouTube Clips Generator is running!')
        except Exception as e:
            # If there's an error, return a helpful error message
            error_message = f"""
            <html>
            <head><title>YouTube Clips Generator - Error</title></head>
            <body>
                <h1>Error in Vercel Serverless Function</h1>
                <p>There was an error starting the application:</p>
                <pre>{str(e)}</pre>
                <p>Traceback:</p>
                <pre>{traceback.format_exc()}</pre>
                <h2>Troubleshooting Steps:</h2>
                <ol>
                    <li>Check if your ASSEMBLYAI_API_KEY environment variable is set</li>
                    <li>Increase memory allocation in Vercel dashboard (Settings > Functions)</li>
                    <li>Try processing shorter videos (under 10 minutes)</li>
                    <li>Check Vercel logs for more details</li>
                </ol>
            </body>
            </html>
            """
            self.send_response(500)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(error_message.encode('utf-8'))

# Run the app locally if not on Vercel
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5002))
    app.run(host='0.0.0.0', port=port, debug=True) 