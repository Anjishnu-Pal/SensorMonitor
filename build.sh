#!/bin/bash
set -e
# Pre-install numpy for host Python (satisfies matplotlib setup_requires)
python -m pip install "numpy<2" --quiet 2>&1
echo "numpy pre-install done"
# Run the build
buildozer android debug 2>&1
