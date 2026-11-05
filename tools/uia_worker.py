"""Private stdio transport for the local UIA client; never an external service."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.uia_service import serve
if __name__=='__main__':serve()
