#!/usr/bin/env python3
import re
import sys
import argparse
from datetime import datetime
from pathlib import Path

def bump_version(current: str, part: str) -> str:
    """Increment the version string."""
    # Remove 'v' prefix if present for calculation
    v_prefix = current.startswith('v')
    v = current[1:] if v_prefix else current
    
    parts = v.split('.')
    if len(parts) != 3:
        # Try to handle simple versions like "0.1"
        while len(parts) < 3:
            parts.append('0')
    
    try:
        major, minor, patch = map(int, parts[:3])
    except ValueError:
        raise ValueError(f"Invalid version components in: {current}")
    
    if part == 'major':
        major += 1
        minor = 0
        patch = 0
    elif part == 'minor':
        minor += 1
        patch = 0
    elif part == 'patch':
        patch += 1
    else:
        raise ValueError(f"Invalid bump part: {part}")
    
    new_v = f"{major}.{minor}.{patch}"
    # Keep the 'v' prefix if the original had it
    return f"v{new_v}" if v_prefix else new_v

def update_readme_version_badge(path: Path, display_version: str, dry_run: bool) -> bool:
    """Update the shield.io version badge in README files."""
    if not path.exists():
        print(f"⚠️  Warning: {path.name} not found. Skipping.")
        return False

    content = path.read_text(encoding="utf-8")
    new_content, count = re.subn(
        r"(https://img\.shields\.io/badge/(?:版本|version)-)v?[\d\.]+(-blueviolet)",
        rf"\g<1>{display_version}\2",
        content,
        count=1,
    )
    if count == 0:
        print(f"⚠️  Warning: version badge not found in {path.name}. Skipping.")
        return False

    if not dry_run:
        path.write_text(new_content, encoding="utf-8")
    print(f"✅ Updated {path.name} version badge")
    return True

def main():
    parser = argparse.ArgumentParser(description="Bump plugin version and update metadata/CHANGELOG")
    parser.add_argument("part", choices=['major', 'minor', 'patch'], help="Which part of the version to bump")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing files")
    
    args = parser.parse_args()
    
    # Updated: now in tools/, so root is parent.parent
    root = Path(__file__).parent.parent
    metadata_path = root / "metadata.yaml"
    changelog_path = root / "CHANGELOG.md"
    readme_paths = [root / "README.md", root / "README_EN.md"]
    
    if not metadata_path.exists():
        print(f"Error: {metadata_path} not found")
        sys.exit(1)
        
    content = metadata_path.read_text(encoding="utf-8")
    # Matches 'version: v0.7.30' or 'version: 0.7.30'
    match = re.search(r"version:\s*(v?[\d\.]+)", content)
    if not match:
        print(f"Error: Version string not found in {metadata_path}")
        sys.exit(1)
        
    current_version_str = match.group(1)
    try:
        new_version_str = bump_version(current_version_str, args.part)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
        
    print(f"Bumping version: {current_version_str} -> {new_version_str}")
    
    display_version = new_version_str if new_version_str.startswith('v') else f"v{new_version_str}"
    if args.dry_run:
        print("Dry run: showing planned file updates.")
        print(f"- {metadata_path}")
        print(f"- {changelog_path}")
        for path in readme_paths:
            print(f"- {path}")
        return
        
    # 1. Update metadata.yaml
    # We replace the exact match to avoid accidental replacements elsewhere
    new_content = content.replace(f"version: {current_version_str}", f"version: {new_version_str}")
    metadata_path.write_text(new_content, encoding="utf-8")
    print(f"✅ Updated {metadata_path.name}")
    
    # 2. Update CHANGELOG.md
    if changelog_path.exists():
        today = datetime.now().strftime("%Y-%m-%d")
        changelog_content = changelog_path.read_text(encoding="utf-8")
        
        # Standard header
        header = "# CHANGELOG"
        
        # New entry template
        entry = f"\n\n## [{display_version}] — {today}\n\n### \n\n- \n"
        
        if header in changelog_content:
            # Insert after the header
            new_changelog = changelog_content.replace(header, header + entry, 1)
            changelog_path.write_text(new_changelog, encoding="utf-8")
            print(f"✅ Updated {changelog_path.name} with new entry template")
        else:
            print("⚠️  Warning: '# CHANGELOG' header not found in CHANGELOG.md. Skipping auto-entry.")

    # 3. Update README badges that mirror the plugin version for marketplace visibility.
    for readme_path in readme_paths:
        update_readme_version_badge(readme_path, display_version, args.dry_run)
            
    print(f"\nNext steps:\n1. Edit CHANGELOG.md to add your changes.\n2. Run 'npm run build' in web/frontend if needed.\n3. Commit and tag.")

if __name__ == "__main__":
    main()
