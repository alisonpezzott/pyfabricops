# Install pyfabricops in development mode
import subprocess
import sys
import os

# Add src directory to Python path
src_path = os.path.join("c:/repos/pyfabricops", "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)
    print(f"📁 Added {src_path} to Python path")

try:
    import pyfabricops
    print("✅ pyfabricops already installed")
except ImportError:
    print("📦 Installing pyfabricops in development mode...")
    result = subprocess.run([sys.executable, "-m", "pip", "install", "-e", "."], 
                          capture_output=True, text=True, cwd="c:/repos/pyfabricops")
    if result.returncode == 0:
        print("✅ pyfabricops installed successfully")
        # Try to import again after installation
        try:
            import pyfabricops
            print("✅ pyfabricops imported successfully")
        except ImportError as e:
            print(f"❌ Still can't import pyfabricops: {e}")
            print("🔄 You may need to restart the kernel")
    else:
        print(f"❌ Error installing pyfabricops: {result.stderr}")
        print(f"📍 Output: {result.stdout}")