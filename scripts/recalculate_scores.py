"""CLI entry point for the shared scoring service."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.scoring import recalculate

if __name__ == "__main__":
    print(f"Recalculated scores for {recalculate()} listings")
