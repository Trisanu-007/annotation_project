#!/bin/bash
# Startup script for the Flask application

# Activate conda environment
source ~/miniconda3/etc/profile.d/conda.sh
conda activate trial

# Start the Flask application
python3 app.py
