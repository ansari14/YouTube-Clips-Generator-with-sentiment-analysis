#!/usr/bin/env python3
"""
Test script to verify that the YouTube Clips Generator works locally.
"""

import os
import sys
import requests
import time
import argparse

def test_local_server(url="http://localhost:5001"):
    """
    Test if the local server is running.
    """
    try:
        response = requests.get(url)
        if response.status_code == 200:
            print(f"✅ Server is running at {url}")
            return True
        else:
            print(f"❌ Server returned status code {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"❌ Could not connect to server at {url}")
        return False

def test_api_key():
    """
    Test if the AssemblyAI API key is set.
    """
    api_key = os.environ.get("ASSEMBLYAI_API_KEY")
    if not api_key:
        print("❌ ASSEMBLYAI_API_KEY environment variable is not set")
        return False
    
    if api_key == "your_api_key_here":
        print("❌ ASSEMBLYAI_API_KEY is set to the default value. Please update it with your actual API key")
        return False
    
    print("✅ ASSEMBLYAI_API_KEY is set")
    return True

def test_ffmpeg():
    """
    Test if ffmpeg is installed.
    """
    try:
        import subprocess
        result = subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode == 0:
            print("✅ ffmpeg is installed")
            return True
        else:
            print("❌ ffmpeg is not installed or not in PATH")
            return False
    except FileNotFoundError:
        print("❌ ffmpeg is not installed or not in PATH")
        return False

def test_yt_dlp():
    """
    Test if yt-dlp is installed.
    """
    try:
        import subprocess
        result = subprocess.run(["yt-dlp", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode == 0:
            print("✅ yt-dlp is installed")
            return True
        else:
            print("❌ yt-dlp is not installed or not in PATH")
            return False
    except FileNotFoundError:
        print("❌ yt-dlp is not installed or not in PATH")
        return False

def main():
    parser = argparse.ArgumentParser(description="Test the YouTube Clips Generator locally")
    parser.add_argument("--url", default="http://localhost:5001", help="URL of the local server")
    args = parser.parse_args()
    
    print("Testing YouTube Clips Generator local setup...")
    
    # Test if server is running
    server_ok = test_local_server(args.url)
    
    # Test if API key is set
    api_key_ok = test_api_key()
    
    # Test if ffmpeg is installed
    ffmpeg_ok = test_ffmpeg()
    
    # Test if yt-dlp is installed
    yt_dlp_ok = test_yt_dlp()
    
    # Print summary
    print("\nTest Summary:")
    print(f"Server: {'✅' if server_ok else '❌'}")
    print(f"API Key: {'✅' if api_key_ok else '❌'}")
    print(f"ffmpeg: {'✅' if ffmpeg_ok else '❌'}")
    print(f"yt-dlp: {'✅' if yt_dlp_ok else '❌'}")
    
    # Check if all tests passed
    all_passed = server_ok and api_key_ok and ffmpeg_ok and yt_dlp_ok
    
    if all_passed:
        print("\n✅ All tests passed! The application should work correctly.")
        return 0
    else:
        print("\n❌ Some tests failed. Please fix the issues before running the application.")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 