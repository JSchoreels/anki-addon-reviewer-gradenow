#!/usr/bin/env python3
"""
Anki Addon Packaging Script
Creates an .ankiaddon file from the current addon directory
"""

import os
import zipfile
import json
import sys
from pathlib import Path

def get_addon_info():
    """Extract addon information from manifest.json"""
    try:
        with open('manifest.json', 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        return manifest.get('name', 'anki-addon'), manifest.get('version', '1.0.0')
    except FileNotFoundError:
        print("Error: manifest.json not found in current directory")
        return None, None
    except json.JSONDecodeError:
        print("Error: Invalid JSON in manifest.json")
        return None, None

def create_addon_package():
    """Create the .ankiaddon package"""
    # Get addon info
    addon_name, version = get_addon_info()
    if not addon_name:
        return False

    # Create package filename
    safe_name = "".join(c for c in addon_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
    safe_name = safe_name.replace(' ', '_')
    package_name = f"{safe_name}_v{version}.ankiaddon"

    # Files to include in the package
    addon_files = [
        '__init__.py',
        'manifest.json',
        'config.json',
        'config.schema.json',
        'README.md'
    ]

    # Check if all required files exist
    missing_files = []
    for file in addon_files:
        if not os.path.exists(file):
            missing_files.append(file)

    if missing_files:
        print(f"Error: Missing required files: {', '.join(missing_files)}")
        return False

    # Create the zip file (ankiaddon is just a zip file with different extension)
    try:
        with zipfile.ZipFile(package_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file in addon_files:
                zipf.write(file, file)
                print(f"Added: {file}")

        print(f"\nSuccessfully created addon package: {package_name}")
        print(f"Package size: {os.path.getsize(package_name)} bytes")

        # Show installation instructions
        print("\nInstallation Instructions:")
        print("1. Open Anki")
        print("2. Go to Tools > Add-ons")
        print("3. Click 'Install from file...'")
        print(f"4. Select the file: {package_name}")
        print("5. Restart Anki")

        return True

    except Exception as e:
        print(f"Error creating package: {str(e)}")
        return False

def main():
    """Main function"""
    print("Anki Addon Packaging Script")
    print("=" * 40)

    # Check if we're in the right directory
    if not os.path.exists('__init__.py'):
        print("Error: This script must be run from the addon directory containing __init__.py")
        sys.exit(1)

    # Create the package
    success = create_addon_package()

    if success:
        print("\nPackaging completed successfully!")
        sys.exit(0)
    else:
        print("\nPackaging failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
