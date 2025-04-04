"""
Test script to print all available routes in the FastAPI app
"""
import sys
import os

# Add the current directory to PATH to make Python properly recognize the package structure
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from api.main import app

print("\n=== Registered Routes ===")
for route in app.routes:
    print(f"{route.methods} {route.path}")
print("========================\n") 