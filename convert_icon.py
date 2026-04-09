import os
import sys
from PIL import Image

def convert_png_to_ico(png_path, ico_output):
    if not os.path.exists(png_path):
        print(f"Error: {png_path} not found.")
        return False
    
    # In case Pillow isn't installed, the build script should handle it, 
    # but we'll try to import and convert here.
    img = Image.open(png_path)
    # Windows icons usually contain multiple sizes
    icon_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(ico_output, format='ICO', sizes=icon_sizes)
    print(f"✅ Success! Icon saved to {ico_output}")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python convert_icon.py <input.png> <output.ico>")
    else:
        convert_png_to_ico(sys.argv[1], sys.argv[2])
