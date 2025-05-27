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

# Constants
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIPS_DIR = os.path.join(BASE_DIR, "clips_output")
TEMP_DIR = os.path.join(BASE_DIR, "temp")

# AssemblyAI API Key - Load from environment variable for security
ASSEMBLYAI_API_KEY = os.environ.get("ASSEMBLYAI_API_KEY", "")
ASSEMBLYAI_HEADERS = {
    "authorization": ASSEMBLYAI_API_KEY,
    "content-type": "application/json"
}

# Configuration for faster processing
FAST_MODE = True  # Always use fast mode for Vercel due to time constraints
MAX_VIDEO_DURATION = 3600  # 1 hour max to prevent very long processing
MAX_CLIP_DURATION = 30  # Duration of clips in seconds
MAX_CLIPS = 5  # Maximum number of clips to generate

# Create directories if running locally (not on Vercel)
if not os.environ.get("VERCEL"):
    os.makedirs(CLIPS_DIR, exist_ok=True)
    os.makedirs(TEMP_DIR, exist_ok=True)

# Store processing status
tasks = {}

def download_youtube_video(url):
    """
    Download a YouTube video using yt-dlp with optimization for faster downloads
    """
    try:
        print(f"Downloading video from {url}...")
        video_id = url.split("v=")[1].split("&")[0]  # Extract video ID
        output_filename = os.path.join(TEMP_DIR, f"{video_id}.mp4")
        
        # Always use lower quality video for faster processing on Vercel
        format_opt = "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best"
        
        # Skip if file already exists and is recent (less than 1 hour old)
        if os.path.exists(output_filename):
            file_age = time.time() - os.path.getmtime(output_filename)
            if file_age < 3600:  # 1 hour in seconds
                print(f"Using existing download at {output_filename}")
                return output_filename, video_id
        
        subprocess.run([
            "yt-dlp",
            "-f", format_opt,
            "--merge-output-format", "mp4",
            "-o", output_filename,
            url
        ], check=True, capture_output=True)
        
        if os.path.exists(output_filename):
            print(f"Downloaded video to {output_filename}")
            return output_filename, video_id
        else:
            raise ValueError("Video download failed")
            
    except Exception as e:
        print(f"Error downloading video: {e}")
        raise

def get_video_duration(video_path):
    """
    Get video duration using ffprobe
    """
    cmd = [
        "ffprobe", 
        "-v", "error", 
        "-show_entries", "format=duration", 
        "-of", "default=noprint_wrappers=1:nokey=1", 
        video_path
    ]
    
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    duration = float(result.stdout)
    
    # Limit processing to MAX_VIDEO_DURATION
    return min(duration, MAX_VIDEO_DURATION)

def extract_audio(video_path, video_id):
    """
    Extract audio from video for transcription with optimized settings
    """
    audio_path = os.path.join(TEMP_DIR, f"{video_id}.mp3")
    
    # Skip if file already exists and is recent
    if os.path.exists(audio_path):
        file_age = time.time() - os.path.getmtime(audio_path)
        if file_age < 3600:  # 1 hour in seconds
            print(f"Using existing audio at {audio_path}")
            return audio_path
    
    # Use lower bitrate for faster processing
    bitrate = "64k"  # Always use lowest bitrate for Vercel
    
    subprocess.run([
        "ffmpeg",
        "-i", video_path,
        "-q:a", "5",  # Lower quality for faster processing
        "-map", "a",
        "-b:a", bitrate,
        "-y",
        audio_path
    ], check=True, capture_output=True)
    
    return audio_path

def transcribe_audio(audio_path, task_id):
    """
    Transcribe audio using AssemblyAI API with sentiment analysis
    """
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
            data=audio_file
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
        headers=ASSEMBLYAI_HEADERS
    )
    
    if transcript_response.status_code != 200:
        raise Exception(f"Error submitting transcription job: {transcript_response.text}")
    
    transcript_id = transcript_response.json()["id"]
    
    # Step 3: Poll for transcription completion
    tasks[task_id]["message"] = "Transcribing audio and analyzing sentiment..."
    tasks[task_id]["progress"] = 30
    
    polling_endpoint = f"https://api.assemblyai.com/v2/transcript/{transcript_id}"
    
    # Check if we've already analyzed a part of this video before
    cached_transcript_path = os.path.join(TEMP_DIR, f"{os.path.basename(audio_path)}.transcript.json")
    if os.path.exists(cached_transcript_path):
        try:
            with open(cached_transcript_path, 'r') as f:
                cached_data = json.load(f)
                if cached_data.get('status') == 'completed':
                    print("Using cached transcript data")
                    return cached_data
        except Exception as e:
            print(f"Error reading cached transcript: {e}")
    
    polling_count = 0
    max_polling = 60  # To prevent infinite loops
    
    while polling_count < max_polling:
        polling_response = requests.get(polling_endpoint, headers=ASSEMBLYAI_HEADERS)
        polling_response_json = polling_response.json()
        
        if polling_response_json["status"] == "completed":
            # Cache the transcript data for future use
            try:
                with open(cached_transcript_path, 'w') as f:
                    json.dump(polling_response_json, f)
            except Exception as e:
                print(f"Error caching transcript: {e}")
                
            return polling_response_json
        elif polling_response_json["status"] == "error":
            raise Exception(f"Transcription error: {polling_response_json['error']}")
        
        print("Waiting for transcription to complete...")
        time.sleep(5)
        polling_count += 1
    
    # If we've waited too long, use a fallback approach
    raise Exception("Transcription timed out - using fallback approach")

def find_engaging_segments(transcript, video_duration, task_id):
    """
    Find the most engaging segments based on sentiment analysis and chapter detection
    Optimized for faster processing
    """
    tasks[task_id]["message"] = "Finding the most engaging moments..."
    tasks[task_id]["progress"] = 40
    
    segments = []
    
    # First check for sentiment analysis results
    if "sentiment_analysis_results" in transcript and transcript["sentiment_analysis_results"]:
        # Filter to only positive sentiments with high confidence
        positive_segments = [
            s for s in transcript["sentiment_analysis_results"]
            if s["sentiment"] == "POSITIVE" and s["confidence"] > 0.7  # Lowered threshold for more results
        ]
        
        # Sort by confidence (highest first)
        positive_segments.sort(key=lambda x: x["confidence"], reverse=True)
        
        # Get timestamps for the top segments
        for segment in positive_segments[:MAX_CLIPS]:
            start_time = segment["start"] / 1000  # Convert from ms to seconds
            
            # Adjust start time to ensure we get 30 seconds (if possible)
            adjusted_start = max(0, start_time - 5)  # Start 5 seconds before for context
            
            segments.append({
                "start_time": adjusted_start,
                "text": segment["text"],
                "sentiment": segment["sentiment"],
                "confidence": segment["confidence"]
            })
    
    # If we don't have enough segments from sentiment analysis, try chapters
    if len(segments) < MAX_CLIPS and "chapters" in transcript and transcript["chapters"]:
        # Sort chapters by summary (most important first)
        chapters = sorted(transcript["chapters"], key=lambda x: x["summary_quality_score"], reverse=True)
        
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
                "text": chapter["headline"],
                "sentiment": "CHAPTER",
                "confidence": chapter["summary_quality_score"]
            })
    
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
    # If video is shorter than 3 clips, just use beginning, middle, end
    if video_duration <= MAX_CLIPS * MAX_CLIP_DURATION:
        return [0, video_duration / 2, max(0, video_duration - MAX_CLIP_DURATION)]
    
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
    
    for word in transcript["words"]:
        word_start = word["start"] / 1000  # Convert from ms to seconds
        word_end = word["end"] / 1000  # Convert from ms to seconds
        
        if word_start >= start_time and word_end <= end_time:
            segment_words.append(word["text"])
            
    return " ".join(segment_words)

def create_clip_with_subtitles(video_path, start_time, duration, output_filename, subtitle_text):
    """
    Create a clip with subtitles using ffmpeg directly for better performance on Vercel
    """
    try:
        # Ensure the output directory exists
        os.makedirs(os.path.dirname(output_filename), exist_ok=True)
        
        # Check if output file already exists
        if os.path.exists(output_filename):
            print(f"Using existing clip: {output_filename}")
            return output_filename
        
        # Create a temporary subtitle file
        subtitle_file = tempfile.NamedTemporaryFile(suffix=".srt", delete=False)
        subtitle_path = subtitle_file.name
        
        # Split subtitle text into lines (max 40 chars per line)
        words = subtitle_text.split()
        lines = []
        current_line = ""
        
        for word in words:
            if len(current_line) + len(word) + 1 > 40:
                lines.append(current_line)
                current_line = word
            else:
                if current_line:
                    current_line += " " + word
                else:
                    current_line = word
                    
        if current_line:
            lines.append(current_line)
            
        # Write subtitle file
        with open(subtitle_path, "w") as f:
            f.write("1\n")
            f.write("00:00:00,000 --> 00:00:30,000\n")
            f.write("\n".join(lines))
        
        # Create vertical clip with subtitles using ffmpeg
        temp_output = output_filename + ".temp.mp4"
        
        # First create the clip with correct aspect ratio
        subprocess.run([
            "ffmpeg",
            "-ss", str(start_time),
            "-i", video_path,
            "-t", str(duration),
            "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black",
            "-c:v", "libx264",
            "-profile:v", "main",
            "-preset", "ultrafast",  # Use ultrafast for Vercel
            "-crf", "28",  # Higher CRF (lower quality) for faster processing
            "-c:a", "aac",
            "-b:a", "128k",
            "-y",
            temp_output
        ], check=True)
        
        # Then add subtitles
        subprocess.run([
            "ffmpeg",
            "-i", temp_output,
            "-vf", f"subtitles={subtitle_path}:force_style='FontSize=24,Alignment=10,BorderStyle=4,Outline=1,Shadow=0,MarginV=30'",
            "-c:v", "libx264",
            "-profile:v", "main",
            "-preset", "ultrafast",  # Use ultrafast for Vercel
            "-crf", "28",  # Higher CRF (lower quality) for faster processing
            "-c:a", "copy",
            "-y",
            output_filename
        ], check=True)
        
        # Clean up temporary files
        os.unlink(subtitle_path)
        if os.path.exists(temp_output):
            os.unlink(temp_output)
        
        print(f"Clip created: {output_filename}")
        return output_filename
        
    except Exception as e:
        print(f"Error creating clip: {e}")
        print(f"Error creating clip {output_filename}: {e}")
        raise

def create_clips_parallel(video_path, segments, task_id, transcript, video_duration, video_id):
    """
    Create clips in parallel for faster processing
    """
    tasks[task_id]["message"] = "Creating clips with subtitles..."
    tasks[task_id]["progress"] = 60
    
    clips = []
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    
    # Prepare clip creation arguments
    clip_args = []
    for i, segment in enumerate(segments, 1):
        start_time = segment["start_time"]
        
        # Get subtitle text from transcript
        subtitle_text = segment["text"]
        if not subtitle_text:
            subtitle_text = get_transcript_segment(transcript, start_time, start_time + MAX_CLIP_DURATION)
            
        # If still no text, use a placeholder
        if not subtitle_text:
            subtitle_text = f"Clip {i} - {int(start_time // 60)}:{int(start_time % 60):02d}"
        
        # Generate output filename
        output_filename = os.path.join(CLIPS_DIR, f"clip_{video_id}_{i}_{timestamp}.mp4")
        
        clip_args.append({
            "video_path": video_path,
            "start_time": start_time,
            "duration": MAX_CLIP_DURATION,
            "output_filename": output_filename,
            "subtitle_text": subtitle_text,
            "segment": segment,
            "clip_id": i
        })
    
    # Create clips in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = []
        for args in clip_args:
            futures.append(executor.submit(
                create_clip_with_subtitles,
                args["video_path"],
                args["start_time"],
                args["duration"],
                args["output_filename"],
                args["subtitle_text"]
            ))
        
        # Process results as they complete
        for i, future in enumerate(concurrent.futures.as_completed(futures)):
            try:
                clip_path = future.result()
                progress = 60 + (i + 1) * 40 // len(futures)
                tasks[task_id]["progress"] = progress
                
                # Add clip to results
                clips.append({
                    "id": clip_args[i]["clip_id"],
                    "path": os.path.relpath(clip_path, BASE_DIR),
                    "start_time": clip_args[i]["start_time"],
                    "text": clip_args[i]["subtitle_text"],
                    "sentiment": clip_args[i]["segment"]["sentiment"],
                    "confidence": clip_args[i]["segment"]["confidence"]
                })
            except Exception as e:
                print(f"Error creating clip {i+1}: {e}")
    
    return clips

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
        
        # Create clips with subtitles
        clips = create_clips_parallel(video_path, segments, task_id, transcript, video_duration, video_id)
        
        # Update task status
        tasks[task_id]["status"] = "completed"
        tasks[task_id]["message"] = f"Successfully created {len(clips)} clips!"
        tasks[task_id]["progress"] = 100
        tasks[task_id]["clips"] = clips
        
    except Exception as e:
        # Handle errors
        tasks[task_id]["status"] = "error"
        tasks[task_id]["message"] = f"Error: {str(e)}"
        tasks[task_id]["progress"] = 0
        print(f"Error processing video: {e}")

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
    # Extract directory path from filename
    directory = os.path.dirname(filename)
    file_name = os.path.basename(filename)
    return send_from_directory(os.path.join(BASE_DIR, directory), file_name)

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

# Vercel serverless handler
def handler(event, context):
    return app(event, context)

# Run the app locally if not on Vercel
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=True) 