import os
import sys
import numpy as np

def main():
    audio_path = "D:\\youtube_search_temp\\fKNhhDb-8xs.m4a"
    if not os.path.exists(audio_path):
        print(f"File not found: {audio_path}")
        return
        
    try:
        import av
        container = av.open(audio_path)
        stream = container.streams.audio[0]
        
        amplitudes = []
        for frame in container.decode(stream):
            # Convert frame to numpy array
            # PyAV frame.to_ndarray() returns float or int array depending on format
            arr = frame.to_ndarray()
            amplitudes.append(np.max(np.abs(arr)))
            
        if amplitudes:
            max_amp = max(amplitudes)
            mean_amp = np.mean(amplitudes)
            print(f"Number of frames analyzed: {len(amplitudes)}")
            print(f"Max amplitude: {max_amp}")
            print(f"Mean amplitude: {mean_amp}")
            if max_amp < 1e-4:
                print("The audio is completely silent or extremely quiet!")
            else:
                print("The audio contains sound/speech!")
        else:
            print("No audio frames decoded!")
            
    except Exception as e:
        print(f"Error analyzing audio: {e}")

if __name__ == "__main__":
    main()
