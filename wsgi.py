#!/usr/bin/env python
"""
WSGI entry point for production deployment
"""
import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.app import app as application

if __name__ == "__main__":
    application.run() 