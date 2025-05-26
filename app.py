from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory
import os
import subprocess
import time
import json
import random
from werkzeug.utils import secure_filename
import threading

# Import functions from podcast_clips.py
from podcast_clips import download_youtube_video, extract_audio, transcribe_audio, find_engaging_moments, create_clip

app = Flask(__name__)

# Constants
OUTPUT_DIR = "/Users/faizanansari/Documents/Clips-cut-url/output"
CLIPS_DIR = os.path.join(OUTPUT_DIR, "clips")

# Ensure output directories exist
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(CLIPS_DIR, exist_ok=True)

# Store processing status
tasks = {}

@app.route('/')
def index():
    return render_template('index.html')

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
    thread = threading.Thread(target=process_video, args=(url, task_id))
    thread.daemon = True
    thread.start()
    
    return redirect(url_for('status', task_id=task_id))

def process_video(url, task_id):
    try:
        # Update status
        tasks[task_id]["message"] = "Downloading video..."
        tasks[task_id]["progress"] = 10
        
        # Download the video
        video_path = download_youtube_video(url)
        
        # Update status
        tasks[task_id]["message"] = "Extracting audio..."
        tasks[task_id]["progress"] = 20
        
        # Extract audio
        audio_path = extract_audio(video_path)
        
        # Update status
        tasks[task_id]["message"] = "Transcribing audio (this may take a while)..."
        tasks[task_id]["progress"] = 30
        
        # Transcribe audio
        transcript = transcribe_audio(audio_path)
        
        # Update status
        tasks[task_id]["message"] = "Finding engaging moments..."
        tasks[task_id]["progress"] = 60
        
        # Find engaging moments
        engaging_moments = find_engaging_moments(transcript)
        
        # Create clips (up to 5)
        tasks[task_id]["message"] = "Creating clips..."
        
        # Sort engaging moments by confidence score
        engaging_moments.sort(key=lambda x: x.get("score", 0), reverse=True)
        
        # If we don't have enough engaging moments, add some random clips
        if len(engaging_moments) < 5:
            words = transcript.get("words", [])
            if words:
                total_duration = (words[-1]["end"] - words[0]["start"]) / 1000  # Convert to seconds
                
                # Add random clips from different parts of the video
                num_to_add = 5 - len(engaging_moments)
                for i in range(num_to_add):
                    # Pick a random starting point (avoid the last 30 seconds)
                    if total_duration > 30:
                        random_start = random.uniform(0, total_duration - 30)
                        engaging_moments.append({
                            "start": random_start,
                            "end": random_start + 30,
                            "score": 0.1,
                            "text": "Random clip"
                        })
        
        # Limit to top 5 moments
        top_moments = engaging_moments[:5]
        
        # Create clips
        clip_paths = []
        for i, moment in enumerate(top_moments):
            tasks[task_id]["progress"] = 60 + (i * 8)  # Increment progress for each clip
            
            # Use 30-second duration for all clips
            start_time = moment["start"]
            duration = 30
            
            # Create the clip
            clip_filename = f"clip_{i+1}"
            clip_path = create_clip(
                video_path,
                start_time,
                duration,
                transcript,
                os.path.join(CLIPS_DIR, clip_filename)
            )
            
            # Store clip information
            if os.path.exists(clip_path):
                relative_path = os.path.relpath(clip_path, OUTPUT_DIR)
                clip_paths.append({
                    "id": i + 1,
                    "path": relative_path,
                    "start_time": start_time,
                    "duration": duration,
                    "text": moment.get("text", "")
                })
        
        # Update task with clip information
        tasks[task_id]["clips"] = clip_paths
        tasks[task_id]["status"] = "completed"
        tasks[task_id]["progress"] = 100
        tasks[task_id]["message"] = "Processing complete!"
        
    except Exception as e:
        # Handle errors
        tasks[task_id]["status"] = "error"
        tasks[task_id]["message"] = f"Error: {str(e)}"
        tasks[task_id]["progress"] = 0

@app.route('/status/<task_id>')
def status(task_id):
    if task_id not in tasks:
        return redirect(url_for('index'))
    
    return render_template('status.html', task=tasks[task_id], task_id=task_id)

@app.route('/download/<path:filename>')
def download_file(filename):
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)

@app.route('/check_status/<task_id>')
def check_status(task_id):
    if task_id not in tasks:
        return jsonify({"error": "Task not found"}), 404
    
    return jsonify(tasks[task_id])

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000) 