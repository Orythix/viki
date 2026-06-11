"""Simple runner for VIKI training via opencode."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.train_viki_opencode import main
main()
