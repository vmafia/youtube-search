import os
import sys

def main():
    audio_path = "D:\\youtube_search_temp\\fKNhhDb-8xs.m4a"
    if not os.path.exists(audio_path):
        print(f"File not found: {audio_path}")
        return
        
    print(f"File size: {os.path.getsize(audio_path)} bytes")
    
    # Try importing av
    try:
        import av
        print("Successfully imported av")
        container = av.open(audio_path)
        print(f"Container format: {container.format.long_name}")
        print(f"Number of streams: {len(container.streams)}")
        for i, stream in enumerate(container.streams):
            print(f"  Stream {i}: type={stream.type}, duration={stream.duration}")
            if stream.type == 'audio':
                print(f"    Sample rate: {stream.rate}, channels: {stream.channels}, layout: {stream.layout.name}")
    except Exception as e:
        print(f"Failed to decode using av: {e}")
        
    # Check if ffmpeg is in PATH
    import shutil
    ffmpeg_path = shutil.which("ffmpeg")
    print(f"ffmpeg path: {ffmpeg_path}")

if __name__ == "__main__":
    main()
