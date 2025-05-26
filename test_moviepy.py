import sys
print(f"Python version: {sys.version}")
print(f"Python path: {sys.path}")

try:
    import moviepy
    print(f"MoviePy version: {moviepy.__version__}")
    print(f"MoviePy path: {moviepy.__file__}")
    
    # Try to import specific modules
    try:
        from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
        print("Successfully imported VideoFileClip, TextClip, CompositeVideoClip")
    except ImportError as e:
        print(f"Error importing from moviepy.editor: {e}")
except ImportError as e:
    print(f"Error importing moviepy: {e}") 