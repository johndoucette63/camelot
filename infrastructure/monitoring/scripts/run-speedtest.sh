#!/bin/bash
# Manual speedtest trigger script
# Usage: ./run-speedtest.sh
# This runs a speedtest immediately and logs results to InfluxDB

set -e

echo "Running manual speedtest..."
docker exec speedtest python -c "
from speedtest_logger import run_speedtest, get_influx_client, write_to_influx

print('Connecting to InfluxDB...')
client = get_influx_client()

print('Running speedtest (this may take 30-60 seconds)...')
results = run_speedtest()

if results:
    write_to_influx(client, results)
    print()
    print('=== Speedtest Results ===')
    print(f'Download: {results[\"download_mbps\"]} Mbps')
    print(f'Upload:   {results[\"upload_mbps\"]} Mbps')
    print(f'Ping:     {results[\"ping_ms\"]} ms')
    print(f'Jitter:   {results[\"jitter_ms\"]} ms')
    print(f'Server:   {results[\"server_name\"]} ({results[\"server_country\"]})')
    print(f'ISP:      {results[\"isp\"]}')
    print()
    print('Results saved to InfluxDB.')
else:
    print('Speedtest failed!')
    exit(1)
"
