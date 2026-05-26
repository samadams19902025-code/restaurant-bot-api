#!/usr/bin/env bash
set -e

cd backend
pip install --upgrade pip
pip install -r requirements.txt
python -m app.db_init

echo "✓ Build complete"
