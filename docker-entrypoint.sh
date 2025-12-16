#!/bin/bash
set -e

# PUID/PGID logic for Unraid/LinuxServer compatibility
PUID=${PUID:-1000}
PGID=${PGID:-1000}

# Update appuser uid/gid if they don't match
if [ "$(id -u appuser)" -ne "$PUID" ] || [ "$(id -g appuser)" -ne "$PGID" ]; then
    echo "Updating appuser to UID: $PUID, GID: $PGID"
    groupmod -o -g "$PGID" appuser
    usermod -o -u "$PUID" -g "$PGID" appuser
fi

# Ensure /data exists and has correct permissions
mkdir -p /data
chown -R appuser:appuser /data

# Fix permissions on /app if needed (though usually read-only is fine, but .venv might need it?)
# generally /app is static code, so we leave it owned by whoever built it (root/1000)
# But if we changed UID, we might want to ensure we can read it.
# For safety, allow appuser to read /app
# chown -R appuser:appuser /app

# Switch to appuser and run the command
echo "Starting application as appuser (UID: $PUID)..."
exec gosu appuser "$@"
