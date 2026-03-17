#!/bin/bash
set -e

# Ensure Gradle uses Java 17+ (required by current Android Gradle plugin)
if command -v java >/dev/null 2>&1; then
	JAVA_MAJOR=$(java -version 2>&1 | awk -F '[\".]' '/version/ {print $2}')
else
	JAVA_MAJOR=0
fi

if [ "${JAVA_MAJOR}" -lt 17 ] && [ -d "/usr/local/sdkman/candidates/java/21.0.9-ms" ]; then
	export JAVA_HOME="/usr/local/sdkman/candidates/java/21.0.9-ms"
	export PATH="$JAVA_HOME/bin:$PATH"
fi

# Pre-install numpy for host Python (satisfies matplotlib setup_requires)
python -m pip install "numpy<2" --quiet 2>&1
echo "numpy pre-install done"
# Run the build
buildozer android debug 2>&1
