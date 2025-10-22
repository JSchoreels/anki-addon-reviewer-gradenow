#!/bin/bash

# MeCab Installation Script for macOS
# This script installs MeCab and the Python bindings

echo "Installing MeCab for Japanese morphological analysis..."

# Check if Homebrew is installed
if ! command -v brew &> /dev/null; then
    echo "Homebrew is not installed. Please install it first from https://brew.sh/"
    exit 1
fi

# Install MeCab and dictionary
echo "Installing MeCab and dictionary..."
brew install mecab
brew install mecab-ipadic

# Install Python MeCab bindings
echo "Installing Python MeCab bindings..."
pip3 install mecab-python3

echo "MeCab installation complete!"
echo ""
echo "To test the installation, you can run:"
echo "python3 -c 'import MeCab; print(MeCab.Tagger(\"-Ochasen\").parse(\"今日は良い天気です\"))'"
