"""
MK3 Amplifier Network Diagnostic Tool

A comprehensive diagnostic tool for troubleshooting network connectivity
and control issues with Sonance MK3 amplifiers.

Usage:
    python -m src.main

Or run directly:
    python src/main.py
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.gui.app import run_app


def main():
    """Main entry point."""
    print("Starting MK3 Amplifier Network Diagnostic Tool...")
    run_app()


if __name__ == "__main__":
    main()
