import re
from pathlib import Path

def get_plugin_version() -> str:
    """Read the plugin version from metadata.yaml (SSOT).
    
    Returns:
        str: The version string, e.g. "0.7.30". Returns "0.0.0" if not found.
    """
    # metadata.yaml is at the project root
    metadata_path = Path(__file__).parent.parent.parent / "metadata.yaml"
    if not metadata_path.exists():
        return "0.0.0"
    
    try:
        content = metadata_path.read_text(encoding="utf-8")
        # Matches 'version: v0.7.30' or 'version: 0.7.30'
        match = re.search(r"version:\s*v?([\d\.]+)", content)
        if match:
            return match.group(1)
    except Exception:
        pass
    
    return "0.0.0"
