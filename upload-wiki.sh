#!/bin/bash
# GitHub Wiki Uploader Script for TycheEngine

WIKI_URL="https://github.com/zt281/TycheEngine.wiki.git"
WIKI_DIR=".wiki-temp"
SOURCE_DIR=".qoder/repowiki/en/content"

# Clone the wiki repo
if [ ! -d "$WIKI_DIR" ]; then
    echo "Cloning wiki repository..."
    git clone "$WIKI_URL" "$WIKI_DIR"
fi

# Copy files maintaining directory structure
cd "$WIKI_DIR"

# Copy new files
echo "Copying wiki files..."
find ../"$SOURCE_DIR" -name "*.md" -type f | while read -r file; do
    # Get relative path from source
    rel_path="${file#../$SOURCE_DIR/}"
    target_dir=$(dirname "$rel_path")

    # Create directory if needed
    if [ "$target_dir" != "." ]; then
        mkdir -p "$target_dir"
    fi

    # Copy file
    cp "$file" "$rel_path"
    echo "  -> $rel_path"
done

# Add all files
git add -A

# Commit
git commit -m "Update wiki documentation - $(date +%Y-%m-%d)"

# Push
git push

cd ..
echo "Wiki updated successfully!"
echo "View at: https://github.com/zt281/TycheEngine/wiki"
