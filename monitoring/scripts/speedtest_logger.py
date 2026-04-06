#!/usr/bin/env python3
"""
Speedtest Logger for Network Monitoring Stack
Runs periodic speedtests and logs results to InfluxDB
"""

import os
import time
import logging
from datetime import datetime
import speedtest
from influxdb import InfluxDBClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration from environment
INFLUXDB_HOST = os.getenv('INFLUXDB_HOST', 'influxdb')
INFLUXDB_PORT = int(os.getenv('INFLUXDB_PORT', 8086))
INFLUXDB_DB = os.getenv('INFLUXDB_DB', 'network_metrics')
INFLUXDB_USER = os.getenv('INFLUXDB_USER', 'grafana')
INFLUXDB_PASSWORD = os.getenv('INFLUXDB_PASSWORD', 'grafanapass')
SPEEDTEST_INTERVAL = int(os.getenv('SPEEDTEST_INTERVAL', 1800))  # 30 min default


def get_influx_client():
    """Create and return InfluxDB client with retry logic."""
    max_retries = 10
    retry_delay = 10

    for attempt in range(max_retries):
        try:
            client = InfluxDBClient(
                host=INFLUXDB_HOST,
                port=INFLUXDB_PORT,
                username=INFLUXDB_USER,
                password=INFLUXDB_PASSWORD,
                database=INFLUXDB_DB
            )
            # Test connection
            client.ping()
            logger.info(f"Connected to InfluxDB at {INFLUXDB_HOST}:{INFLUXDB_PORT}")
            return client
        except Exception as e:
            logger.warning(f"InfluxDB connection attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)

    raise Exception("Failed to connect to InfluxDB after maximum retries")


def run_speedtest():
    """Run speedtest and return results."""
    logger.info("Starting speedtest...")

    try:
        st = speedtest.Speedtest()
        st.get_best_server()

        # Run tests
        download_speed = st.download() / 1_000_000  # Convert to Mbps
        upload_speed = st.upload() / 1_000_000  # Convert to Mbps

        results = st.results.dict()

        return {
            'download_mbps': round(download_speed, 2),
            'upload_mbps': round(upload_speed, 2),
            'ping_ms': round(results['ping'], 2),
            'jitter_ms': round(results.get('jitter', 0), 2) if results.get('jitter') else 0,
            'server_name': results['server']['name'],
            'server_host': results['server']['host'],
            'server_country': results['server']['country'],
            'server_id': results['server']['id'],
            'isp': results.get('client', {}).get('isp', 'Unknown'),
            'timestamp': results['timestamp']
        }
    except Exception as e:
        logger.error(f"Speedtest failed: {e}")
        return None


def write_to_influx(client, results):
    """Write speedtest results to InfluxDB."""
    if not results:
        return False

    json_body = [
        {
            "measurement": "speedtest",
            "tags": {
                "server_name": results['server_name'],
                "server_host": results['server_host'],
                "server_country": results['server_country'],
                "isp": results['isp']
            },
            "time": datetime.utcnow().isoformat() + "Z",
            "fields": {
                "download_mbps": float(results['download_mbps']),
                "upload_mbps": float(results['upload_mbps']),
                "ping_ms": float(results['ping_ms']),
                "jitter_ms": float(results['jitter_ms']),
                "server_id": int(results['server_id'])
            }
        }
    ]

    try:
        client.write_points(json_body)
        logger.info(
            f"Speedtest results written: "
            f"Download: {results['download_mbps']} Mbps, "
            f"Upload: {results['upload_mbps']} Mbps, "
            f"Ping: {results['ping_ms']} ms, "
            f"Server: {results['server_name']}"
        )
        return True
    except Exception as e:
        logger.error(f"Failed to write to InfluxDB: {e}")
        return False


def main():
    """Main loop - run speedtests at regular intervals."""
    logger.info(f"Speedtest Logger starting - interval: {SPEEDTEST_INTERVAL}s ({SPEEDTEST_INTERVAL // 60} minutes)")

    # Wait a bit for InfluxDB to be ready
    time.sleep(30)

    client = get_influx_client()

    # Run initial speedtest
    results = run_speedtest()
    write_to_influx(client, results)

    while True:
        logger.info(f"Sleeping for {SPEEDTEST_INTERVAL} seconds until next speedtest...")
        time.sleep(SPEEDTEST_INTERVAL)

        try:
            results = run_speedtest()
            write_to_influx(client, results)
        except Exception as e:
            logger.error(f"Error during speedtest cycle: {e}")
            # Try to reconnect to InfluxDB
            try:
                client = get_influx_client()
            except Exception:
                pass


if __name__ == '__main__':
    main()
