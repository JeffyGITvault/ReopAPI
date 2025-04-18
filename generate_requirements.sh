#!/bin/bash

# Path to your project
PROJECT_DIR="/workspaces/ReopAPI"

# Step 1: Run pipreqs and overwrite requirements.txt
echo "Running pipreqs..."
pipreqs "$PROJECT_DIR" --force

# Step 2: Fix common casing issues
echo "Fixing casing in requirements.txt..."
sed -i 's/^Requests==/requests==/g' "$PROJECT_DIR/requirements.txt"
sed -i 's/^Numpy==/numpy==/g' "$PROJECT_DIR/requirements.txt"
sed -i 's/^Pandas==/pandas==/g' "$PROJECT_DIR/requirements.txt"
sed -i 's/^Scikit-learn==/scikit-learn==/g' "$PROJECT_DIR/requirements.txt"
sed -i 's/^Matplotlib==/matplotlib==/g' "$PROJECT_DIR/requirements.txt"
sed -i 's/^Seaborn==/seaborn==/g' "$PROJECT_DIR/requirements.txt"

echo "requirements.txt updated and cleaned."
