#!/usr/bin/env python3
"""GeoLog — quick start script."""
import subprocess
import sys
import os

def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    port = sys.argv[1] if len(sys.argv) > 1 else "8000"
    print(f"🚀 Starting GeoLog on http://localhost:{port}")
    subprocess.run([
        sys.executable, "-m", "uvicorn",
        "backend.main:app",
        "--host", "0.0.0.0",
        "--port", port,
        "--reload",
    ])

if __name__ == "__main__":
    main()
