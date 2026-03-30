#!/bin/bash
# Start DB container if not running
docker start anywhere2opus_db 2>/dev/null || true

# Wait up to 60 seconds for PostgreSQL to be ready
echo "Waiting for PostgreSQL to be ready..."
TRIES=0
until docker exec anywhere2opus_db pg_isready -U anywhere2opus -q; do
    TRIES=$((TRIES + 1))
    if [ "$TRIES" -ge 30 ]; then
        echo "PostgreSQL did not become ready in time."
        exit 1
    fi
    echo "Attempt $TRIES/30 - PostgreSQL not ready yet, waiting 2s..."
    sleep 2
done
echo "PostgreSQL is ready."
