#!/usr/bin/env python
"""
Main entry point for the Screen WebApp application
"""
import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.app import app

if __name__ == '__main__':
    # Development server
    app.run(debug=True, host='0.0.0.0', port=5001) 