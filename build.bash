#!/bin/bash

# Create virtual environment if it doesn't exist
if [ ! -d "python-env" ]; then
    python3 -m venv python-env
fi

# Activate the environment
source python-env/bin/activate

# Ensure requirements file exists with needed packages
if [ ! -f requirements.txt ]; then
    echo "Creating requirements.txt with dependencies..."
    
    cat <<EOL > requirements.txt
ebooklib
tkhtmlview
python-dotenv
tweepy
instagrapi
EOL
fi

# Install dependencies
pip install -r requirements.txt

# Run the app
python3 main.py
