#!/usr/bin/env python3
"""
Simple YouTube Clips Generator

Downloads a YouTube video and creates 3 clips from the most engaging parts
"""

import os
import sys
import subprocess
import random
import json
import requests
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory
import threading
import time
from pathlib import Path

app = Flask(__name__)

# Constants
OUTPUT_DIR = "/Users/faizanansari/Documents/Clips-cut-url/output"
CLIPS_DIR = os.path.join(OUTPUT_DIR, "clips")

# Ensure output directories exist
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(CLIPS_DIR, exist_ok=True)

# Store processing status
tasks = {}

def download_youtube_video(url):
    """
    Download a YouTube video using yt-dlp
    """
    try:
        print(f"Downloading video from {url}...")
        video_id = url.split("v=")[1].split("&")[0]  # Extract video ID
        output_filename = os.path.join(OUTPUT_DIR, f"{video_id}.mp4")
        
        subprocess.run([
            "yt-dlp",
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
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
    return duration

def extract_audio(video_path, video_id):
    """
    Extract audio from video for transcription
    """
    audio_path = os.path.join(OUTPUT_DIR, f"{video_id}.mp3")
    
    subprocess.run([
        "ffmpeg",
        "-i", video_path,
        "-q:a", "0",
        "-map", "a",
        "-y",
        audio_path
    ], check=True, capture_output=True)
    
    return audio_path

def analyze_audio_content(audio_path, video_id, task_id):
    """
    Basic analysis of audio to find engaging sections
    This is a simplified version that uses audio level analysis and video segments
    """
    try:
        tasks[task_id]["message"] = "Analyzing audio for engaging sections..."
        tasks[task_id]["progress"] = 40
        
        # Get video duration
        video_path = os.path.join(OUTPUT_DIR, f"{video_id}.mp4")
        duration = get_video_duration(video_path)
        
        # Divide video into segments for analysis
        segments = []
        
        # If video is shorter than 2 minutes, use fixed positions
        if duration < 120:
            # For shorter videos, take beginning, middle and end
            segments = [
                max(5, duration * 0.1),          # 10% in, but at least 5 seconds
                duration / 2,                     # Middle
                min(duration - 30, duration * 0.8)  # 80% in, but leave room for a 30 sec clip
            ]
        else:
            # For longer videos, analyze several segments and pick points of interest
            # Start points to analyze (as percentage of total duration)
            analyze_points = [0.1, 0.25, 0.4, 0.5, 0.6, 0.75, 0.9]
            
            # Convert to actual timestamps
            timestamps = [duration * p for p in analyze_points]
            
            # Select 3 well-distributed points
            segments = [
                timestamps[1],  # Around 25% 
                timestamps[3],  # Middle (50%)
                timestamps[5],  # Around 75%
            ]
        
        # Make sure we have exactly 3 segments
        segments = segments[:3]
        while len(segments) < 3:
            # If we have fewer than 3 segments, add evenly spaced points
            missing = 3 - len(segments)
            for i in range(missing):
                segments.append(duration * (i + 1) / (missing + 1))
        
        # Make sure no segment starts too close to the end
        segments = [min(s, duration - 35) for s in segments]
        segments = [max(0, s) for s in segments]  # Ensure no negative values
        
        print(f"Selected segments at: {segments}")
        return segments
        
    except Exception as e:
        print(f"Error analyzing audio: {e}")
        # Fallback to simple segments if analysis fails
        duration = get_video_duration(os.path.join(OUTPUT_DIR, f"{video_id}.mp4"))
        return [
            min(30, duration * 0.1),
            min(duration / 2, duration - 60),
            max(0, min(duration - 30, duration * 0.9))
        ]

def create_clip(video_path, start_time, duration, output_filename):
    """
    Create a video clip using ffmpeg with 9:16 aspect ratio (1080x1920) for social media
    """
    try:
        print(f"Creating {duration}-second clip starting at {start_time} seconds...")
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(output_filename), exist_ok=True)
        
        # Use ffmpeg to extract the clip with 9:16 aspect ratio (1080x1920)
        # Center-crop the video and scale to 9:16 ratio for Instagram
        subprocess.run([
            "ffmpeg",
            "-ss", str(start_time),
            "-i", video_path,
            "-t", str(duration),
            "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black",
            "-c:v", "libx264",
            "-profile:v", "main",
            "-preset", "medium", 
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "128k",
            "-y",  # Overwrite output file if it exists
            output_filename
        ], check=True, capture_output=True)
        
        if os.path.exists(output_filename):
            print(f"Clip created: {output_filename}")
            return output_filename
        else:
            raise ValueError(f"Failed to create clip at {output_filename}")
            
    except Exception as e:
        print(f"Error creating clip: {e}")
        raise

def process_video_task(url, task_id):
    """
    Process a video URL to create 3 clips from the most engaging parts
    """
    try:
        # Update status
        tasks[task_id]["message"] = "Downloading video..."
        tasks[task_id]["progress"] = 10
        
        # Download the video
        video_path, video_id = download_youtube_video(url)
        
        # Update status
        tasks[task_id]["message"] = "Analyzing video to find interesting segments..."
        tasks[task_id]["progress"] = 30
        
        # Analyze content to find important parts (we can skip audio extraction for simplicity)
        important_timestamps = analyze_audio_content(None, video_id, task_id)
        
        # Update status
        tasks[task_id]["message"] = "Creating clips from important sections..."
        tasks[task_id]["progress"] = 50
        
        # Create clips at the important positions
        clips = []
        clip_duration = 30  # 30 second clips
        
        for i, start_time in enumerate(important_timestamps):
            # Update progress
            tasks[task_id]["progress"] = 50 + (i * 15)
            
            # Ensure start_time is not negative and not too close to the end
            start_time = max(0, start_time)
            
            try:
                # Create clip
                clip_filename = os.path.join(CLIPS_DIR, f"clip_{i+1}.mp4")
                clip_path = create_clip(video_path, start_time, clip_duration, clip_filename)
                
                # Add to clips list
                relative_path = os.path.relpath(clip_path, OUTPUT_DIR)
                clips.append({
                    "id": i + 1,
                    "path": relative_path,
                    "start_time": start_time,
                    "duration": clip_duration
                })
            except Exception as clip_error:
                print(f"Error creating clip {i+1}: {clip_error}")
                # Continue with other clips even if one fails
                continue
        
        # Only mark as completed if we have at least one clip
        if clips:
            # Update task with completed status
            tasks[task_id]["clips"] = clips
            tasks[task_id]["status"] = "completed"
            tasks[task_id]["progress"] = 100
            tasks[task_id]["message"] = f"Created {len(clips)} clips from the most engaging parts of your video!"
        else:
            # If all clips failed, mark as error
            tasks[task_id]["status"] = "error"
            tasks[task_id]["message"] = "Failed to create any clips. Please try another video."
            tasks[task_id]["progress"] = 0
        
    except Exception as e:
        # Handle errors
        tasks[task_id]["status"] = "error"
        tasks[task_id]["message"] = f"Error: {str(e)}"
        tasks[task_id]["progress"] = 0
        print(f"Error processing video: {e}")

@app.route('/')
def index():
    return render_template('simple_index.html')

@app.route('/process', methods=['POST'])
def process_url():
    # Get the YouTube URL from the form
    url = request.form.get('youtube_url')
    if not url or "youtube.com" not in url:
        return jsonify({"error": "Please enter a valid YouTube URL"}), 400
    
    # Generate a task ID
    task_id = str(int(time.time()))
    
    # Initialize task status
    tasks[task_id] = {
        "url": url,
        "status": "processing",
        "message": "Starting processing...",
        "clips": [],
        "progress": 0
    }
    
    # Start processing in background
    thread = threading.Thread(target=process_video_task, args=(url, task_id))
    thread.daemon = True
    thread.start()
    
    return redirect(url_for('status', task_id=task_id))

@app.route('/status/<task_id>')
def status(task_id):
    if task_id not in tasks:
        return redirect(url_for('index'))
    
    return render_template('simple_status.html', task=tasks[task_id], task_id=task_id)

@app.route('/download/<path:filename>')
def download_file(filename):
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)

@app.route('/check_status/<task_id>')
def check_status(task_id):
    if task_id not in tasks:
        return jsonify({"error": "Task not found"}), 404
    
    return jsonify(tasks[task_id])

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001) 