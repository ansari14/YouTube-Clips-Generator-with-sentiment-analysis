#!/usr/bin/env python3
"""
YouTube Podcast Clips Generator

Downloads a YouTube video and creates 5 clips from the most engaging parts based on sentiment analysis.
Adds subtitles and optimizes for Instagram (9:16 aspect ratio).
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
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip, ColorClip

app = Flask(__name__)

# Constants
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLIPS_DIR = os.path.join(BASE_DIR, "clips_output")
TEMP_DIR = os.path.join(BASE_DIR, "temp")

# AssemblyAI API Key - Replace with your own API key
ASSEMBLYAI_API_KEY = "9abcbb4b67c14ad889c85c2f68-----1"
ASSEMBLYAI_HEADERS = {
    "authorization": ASSEMBLYAI_API_KEY,
    "content-type": "application/json"
}

# Configuration for faster processing
FAST_MODE = True  # Set to False for higher quality but slower processing
MAX_VIDEO_DURATION = 3600  # 1 hour max to prevent very long processing
MAX_CLIP_DURATION = 30  # Duration of clips in seconds
MAX_CLIPS = 5  # Maximum number of clips to generate

# Ensure output directories exist
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
        
        # If fast mode is enabled, use lower quality video for faster processing
        format_opt = "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best" if FAST_MODE else "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        
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
    bitrate = "64k" if FAST_MODE else "128k"
    
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
    
    # If we don't have enough segments from sentiment analysis, use chapters
    if len(segments) < MAX_CLIPS and "chapters" in transcript and transcript["chapters"]:
        chapters = transcript["chapters"]
        
        # Sort chapters by gist (summary) to find important ones
        chapters.sort(key=lambda x: len(x["summary"]), reverse=True)
        
        for chapter in chapters[:MAX_CLIPS - len(segments)]:
            start_time = chapter["start"] / 1000  # Convert from ms to seconds
            
            # Take a segment from 10 seconds into the chapter
            chapter_start = start_time + 10
            
            # Make sure we're not too close to the end
            if chapter_start + MAX_CLIP_DURATION < video_duration:
                segments.append({
                    "start_time": chapter_start,
                    "text": chapter["summary"],
                    "sentiment": "CHAPTER",
                    "confidence": 0.7  # Default confidence for chapters
                })
    
    # If we still don't have enough segments, fall back to default timestamps
    if len(segments) < MAX_CLIPS:
        # Use smart timestamp selection as a fallback
        fallback_timestamps = get_fallback_timestamps(video_duration)
        
        for i, start_time in enumerate(fallback_timestamps[:MAX_CLIPS - len(segments)]):
            segments.append({
                "start_time": start_time,
                "text": f"Clip {len(segments) + 1}",
                "sentiment": "FALLBACK",
                "confidence": 0.5  # Lower confidence for fallback
            })
    
    # Ensure segments are not too close to each other
    filtered_segments = []
    for segment in segments:
        # Check if this segment is at least 30 seconds away from any existing filtered segment
        if not any(abs(segment["start_time"] - existing["start_time"]) < MAX_CLIP_DURATION 
                  for existing in filtered_segments):
            filtered_segments.append(segment)
            
            # Make sure we're not exceeding the video duration
            if segment["start_time"] + MAX_CLIP_DURATION > video_duration:
                segment["start_time"] = max(0, video_duration - MAX_CLIP_DURATION)
    
    # Return the best segments based on confidence
    filtered_segments.sort(key=lambda x: x["confidence"], reverse=True)
    return filtered_segments[:MAX_CLIPS]

def get_fallback_timestamps(video_duration):
    """
    Get fallback timestamps if sentiment analysis doesn't provide good results
    """
    # If video is shorter than 2 minutes, use fixed positions
    if video_duration < 120:
        # For shorter videos, take beginning, middle and end
        return [
            max(5, video_duration * 0.1),         # 10% in, but at least 5 seconds
            video_duration / 2,                    # Middle
            min(video_duration - MAX_CLIP_DURATION, video_duration * 0.8)  # 80% in, but leave room for a clip
        ]
    else:
        # For longer videos, use distributed timestamps
        return [
            video_duration * 0.25,  # 25% in
            video_duration * 0.5,   # 50% in (middle)
            video_duration * 0.75,  # 75% in
            video_duration * 0.15,  # 15% in
            video_duration * 0.85,  # 85% in
        ]

def get_transcript_segment(transcript, start_time, end_time):
    """
    Extract transcript text for a specific segment
    """
    if "words" not in transcript or not transcript["words"]:
        return ""
    
    # Convert to milliseconds for comparison with transcript
    start_ms = start_time * 1000
    end_ms = end_time * 1000
    
    # Get words that fall within the segment
    segment_words = [
        word for word in transcript["words"]
        if start_ms <= word["start"] <= end_ms or 
           start_ms <= word["end"] <= end_ms or
           (word["start"] <= start_ms and word["end"] >= end_ms)
    ]
    
    # Return the text of those words
    return " ".join(word["text"] for word in segment_words)

def create_clip_with_subtitles(video_path, start_time, duration, output_filename, subtitle_text):
    """
    Create a video clip with subtitles using ffmpeg
    Optimized for faster processing
    """
    try:
        print(f"Creating {duration}-second clip starting at {start_time} seconds...")
        
        # Use existing clip if it exists (based on filename pattern)
        base_name = os.path.basename(output_filename)
        pattern = base_name.split('_')[0] + '_' + base_name.split('_')[1] + '_' + base_name.split('_')[2]
        
        for existing_file in os.listdir(CLIPS_DIR):
            if pattern in existing_file and os.path.exists(os.path.join(CLIPS_DIR, existing_file)):
                # Use existing file if it's less than a day old
                existing_path = os.path.join(CLIPS_DIR, existing_file)
                file_age = time.time() - os.path.getmtime(existing_path)
                if file_age < 86400:  # 24 hours in seconds
                    print(f"Using existing clip: {existing_path}")
                    return existing_path
        
        # First create the clip without subtitles using ffmpeg
        temp_clip_path = output_filename + ".temp.mp4"
        
        # Use optimized settings for faster processing
        video_quality = "28" if FAST_MODE else "23"  # Higher CRF = lower quality, faster encoding
        preset = "ultrafast" if FAST_MODE else "medium"  # ultrafast = fastest encoding
        
        # Step 1: Use ffmpeg to extract the clip with 9:16 aspect ratio (1080x1920)
        # With optimized settings for faster processing
        subprocess.run([
            "ffmpeg",
            "-ss", str(start_time),
            "-i", video_path,
            "-t", str(duration),
            "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black",
            "-c:v", "libx264",
            "-profile:v", "baseline",  # Faster encoding
            "-preset", preset, 
            "-crf", video_quality,
            "-c:a", "aac",
            "-b:a", "64k",  # Lower audio quality for faster processing
            "-y",
            temp_clip_path
        ], check=True, capture_output=True)
        
        # Step 2: Add subtitles using ffmpeg if subtitle text is available
        if subtitle_text and not FAST_MODE:
            # Create subtitle file
            srt_path = temp_clip_path + ".srt"
            with open(srt_path, 'w') as f:
                f.write("1\n")
                f.write("00:00:00,000 --> 00:00:30,000\n")
                f.write(subtitle_text)
            
            # Add subtitles to video
            final_clip_path = output_filename
            subprocess.run([
                "ffmpeg",
                "-i", temp_clip_path,
                "-vf", f"subtitles={srt_path}:force_style='FontSize=24,Alignment=10,BorderStyle=4,Outline=1,Shadow=0,MarginV=35'",
                "-c:v", "libx264",
                "-preset", preset,
                "-crf", video_quality,
                "-c:a", "copy",
                "-y",
                final_clip_path
            ], check=True, capture_output=True)
            
            # Clean up
            if os.path.exists(temp_clip_path):
                os.remove(temp_clip_path)
            if os.path.exists(srt_path):
                os.remove(srt_path)
                
            if os.path.exists(final_clip_path):
                print(f"Clip created: {final_clip_path}")
                return final_clip_path
            else:
                raise ValueError(f"Failed to create clip with subtitles at {final_clip_path}")
        else:
            # If no subtitle text or in fast mode, just rename the temp file
            os.rename(temp_clip_path, output_filename)
            if os.path.exists(output_filename):
                print(f"Clip created: {output_filename}")
                return output_filename
            else:
                raise ValueError(f"Failed to create clip at {output_filename}")
            
    except Exception as e:
        print(f"Error creating clip: {e}")
        # If subtitles fail, try to use the basic clip if it exists
        if os.path.exists(temp_clip_path):
            os.rename(temp_clip_path, output_filename)
            return output_filename
        raise

def create_clips_parallel(video_path, segments, task_id, transcript, video_duration, video_id):
    """
    Create clips in parallel to speed up processing
    """
    clip_duration = MAX_CLIP_DURATION
    clips = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(segments), 3)) as executor:
        future_to_segment = {}
        
        for i, segment in enumerate(segments):
            # Ensure start_time is not negative and not too close to the end
            start_time = max(0, segment["start_time"])
            
            # Get transcript text for the segment
            segment_text = segment.get("text", "")
            
            if "FALLBACK" not in segment.get("sentiment", ""):
                try:
                    # Try to get more accurate subtitle text from transcript
                    segment_text = get_transcript_segment(
                        transcript, 
                        start_time, 
                        min(start_time + clip_duration, video_duration)
                    ) or segment_text
                except Exception as text_error:
                    print(f"Error getting transcript segment: {text_error}")
            
            # Create clip with subtitles
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            clip_filename = os.path.join(CLIPS_DIR, f"clip_{video_id}_{i+1}_{timestamp}.mp4")
            
            # Submit clip creation to the thread pool
            future = executor.submit(
                create_clip_with_subtitles,
                video_path,
                start_time,
                clip_duration,
                clip_filename,
                segment_text
            )
            
            future_to_segment[future] = {
                "id": i + 1,
                "start_time": start_time,
                "duration": clip_duration,
                "text": segment_text,
                "sentiment": segment.get("sentiment", "NEUTRAL"),
                "confidence": segment.get("confidence", 0.5)
            }
        
        # Process completed futures
        for i, future in enumerate(concurrent.futures.as_completed(future_to_segment)):
            segment = future_to_segment[future]
            tasks[task_id]["progress"] = 50 + ((i + 1) * 50 // len(segments))
            
            try:
                clip_path = future.result()
                relative_path = os.path.relpath(clip_path, BASE_DIR)
                
                clips.append({
                    "id": segment["id"],
                    "path": relative_path,
                    "start_time": segment["start_time"],
                    "duration": segment["duration"],
                    "text": segment["text"],
                    "sentiment": segment["sentiment"],
                    "confidence": segment["confidence"]
                })
                
            except Exception as e:
                print(f"Error creating clip {segment['id']}: {e}")
    
    return clips

def process_video_task(url, task_id):
    """
    Process a video URL to create clips from the most engaging parts
    """
    try:
        # Update status
        tasks[task_id]["message"] = "Downloading video..."
        tasks[task_id]["progress"] = 10
        
        # Download the video
        video_path, video_id = download_youtube_video(url)
        
        # Get video duration
        video_duration = get_video_duration(video_path)
        
        # Extract audio for transcription
        audio_path = extract_audio(video_path, video_id)
        
        # Transcribe and analyze the audio
        try:
            transcript = transcribe_audio(audio_path, task_id)
            
            # Find engaging segments based on sentiment analysis
            segments = find_engaging_segments(transcript, video_duration, task_id)
        except Exception as e:
            print(f"Error in transcription or sentiment analysis: {e}")
            # Fallback to timestamp-based selection
            video_duration = get_video_duration(video_path)
            fallback_timestamps = get_fallback_timestamps(video_duration)[:MAX_CLIPS]
            
            segments = [
                {
                    "start_time": ts,
                    "text": f"Clip {i+1}",
                    "sentiment": "FALLBACK",
                    "confidence": 0.5
                }
                for i, ts in enumerate(fallback_timestamps)
            ]
        
        # Update status
        tasks[task_id]["message"] = "Creating clips from engaging sections..."
        tasks[task_id]["progress"] = 50
        
        # Create clips at the engaging positions (in parallel for speed)
        clips = create_clips_parallel(video_path, segments, task_id, transcript, video_duration, video_id)
        
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
    
    finally:
        # Clean up temporary files
        try:
            temp_files = [f for f in os.listdir(TEMP_DIR) if f.endswith(('.mp4.temp.mp4', '.mp4.temp.m4a', '.srt'))]
            for file in temp_files:
                file_path = os.path.join(TEMP_DIR, file)
                if os.path.isfile(file_path):
                    os.remove(file_path)
        except Exception as cleanup_error:
            print(f"Error cleaning up temporary files: {cleanup_error}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate-clips', methods=['POST'])
def generate_clips():
    """
    API endpoint to generate clips from a YouTube URL
    """
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
    
    return render_template('status.html', task=tasks[task_id], task_id=task_id)

@app.route('/download/<path:filename>')
def download_file(filename):
    # Extract directory path from filename
    file_dir = os.path.dirname(os.path.join(BASE_DIR, filename))
    file_name = os.path.basename(filename)
    
    return send_from_directory(file_dir, file_name, as_attachment=True)

@app.route('/check_status/<task_id>')
def check_status(task_id):
    if task_id not in tasks:
        return jsonify({"error": "Task not found"}), 404
    
    return jsonify(tasks[task_id])

@app.route('/api/generate-clips', methods=['POST'])
def api_generate_clips():
    """
    API endpoint to generate clips from a YouTube URL
    Returns JSON with clip info
    """
    data = request.get_json()
    url = data.get('youtube_url')
    
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
    
    return jsonify({"task_id": task_id, "status": "processing"})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001) 
