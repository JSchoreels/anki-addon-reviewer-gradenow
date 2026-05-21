#!/usr/bin/env python3
"""
Anki Addon Development Helper Script
Automatically copies addon files to Anki's addons directory for faster testing
"""

import os
import shutil
import sys
import json
from pathlib import Path

def get_anki_addons_dir():
    """Find the Anki addons directory based on the OS"""
    home = Path.home()

    # Try different possible locations
    possible_paths = [
        home / "Library" / "Application Support" / "Anki2" / "addons21",  # macOS
        home / "AppData" / "Roaming" / "Anki2" / "addons21",              # Windows
        home / ".local" / "share" / "Anki2" / "addons21",                 # Linux
        home / "Documents" / "Anki2" / "addons21",                        # Alternative
    ]

    for path in possible_paths:
        if path.exists():
            return path

    return None

def get_addon_info():
    """Get addon information from manifest.json"""
    try:
        with open('manifest.json', 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        return manifest.get('package', 'reviewer_gradenow'), manifest.get('name', 'Reviewer Grade Now')
    except FileNotFoundError:
        print("Error: manifest.json not found in current directory")
        return None, None
    except json.JSONDecodeError:
        print("Error: Invalid JSON in manifest.json")
        return None, None

def copy_addon_to_anki(anki_dir, addon_id):
    """Copy addon files to Anki directory"""
    addon_target_dir = anki_dir / addon_id

    # Files to copy
    addon_files = [
        '__init__.py',
        'grade_dialog.py',
        'grading.py',
        'mecab.py',
        'search.py',
        'manifest.json',
        'config.json',
        'config.schema.json',
        'docs/GRADING.MD',
    ]

    # Create target directory if it doesn't exist
    addon_target_dir.mkdir(exist_ok=True)

    # Copy files
    copied_files = []
    for file in addon_files:
        if os.path.exists(file):
            target_file = addon_target_dir / file
            target_file.parent.mkdir(exist_ok=True)
            shutil.copy2(file, target_file)
            copied_files.append(file)
            print(f"Copied: {file} -> {target_file}")
        else:
            print(f"Warning: {file} not found, skipping")

    return copied_files

def remove_old_addon(anki_dir, addon_id):
    """Remove old addon files to ensure clean install"""
    addon_target_dir = anki_dir / addon_id

    if addon_target_dir.exists():
        try:
            shutil.rmtree(addon_target_dir)
            print(f"Removed old addon directory: {addon_target_dir}")
            return True
        except Exception as e:
            print(f"Warning: Could not remove old addon directory: {e}")
            return False
    return True

def main():
    """Main function"""
    print("Anki Addon Development Helper")
    print("=" * 40)

    # Check if we're in the right directory
    if not os.path.exists('__init__.py'):
        print("Error: This script must be run from the addon directory containing __init__.py")
        sys.exit(1)

    # Get addon info
    addon_id, addon_name = get_addon_info()
    if not addon_id:
        sys.exit(1)

    print(f"Addon ID: {addon_id}")
    print(f"Addon Name: {addon_name}")

    # Find Anki addons directory
    anki_addons_dir = get_anki_addons_dir()
    if not anki_addons_dir:
        print("Error: Could not find Anki addons directory")
        print("Please make sure Anki is installed and has been run at least once")
        sys.exit(1)

    print(f"Anki addons directory: {anki_addons_dir}")

    # Ask for confirmation
    response = input(f"\\nCopy addon to Anki? This will overwrite existing files. (y/N): ")
    if response.lower() not in ['y', 'yes']:
        print("Operation cancelled")
        sys.exit(0)

    try:
        # Remove old addon first for clean install
        remove_old_addon(anki_addons_dir, addon_id)

        # Copy addon files
        copied_files = copy_addon_to_anki(anki_addons_dir, addon_id)

        if copied_files:
            print(f"\\nSuccessfully copied {len(copied_files)} files to Anki!")
            print(f"Target directory: {anki_addons_dir / addon_id}")

            print("\\nNext steps:")
            print("1. Restart Anki to load the updated addon")
            print("2. Test your changes in the reviewer")
            print("3. Run this script again after making code changes")

            # Check if Anki might be running
            print("\\nNote: If Anki is currently running, you'll need to restart it to see changes")
        else:
            print("\\nNo files were copied!")

    except Exception as e:
        print(f"\\nError copying addon: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
