#!/usr/bin/env python3
"""
Smokeping to InfluxDB Exporter
Parses Smokeping RRD data and exports to InfluxDB for Grafana visualization
"""

import os
import time
import logging
import subprocess
from datetime import datetime
from pathlib import Path
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
SMOKEPING_DATA_DIR = os.getenv('SMOKEPING_DATA_DIR', '/smokeping-data')
EXPORT_INTERVAL = int(os.getenv('EXPORT_INTERVAL', 60))  # seconds


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
            client.ping()
            logger.info(f"Connected to InfluxDB at {INFLUXDB_HOST}:{INFLUXDB_PORT}")
            return client
        except Exception as e:
            logger.warning(f"InfluxDB connection attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)

    raise Exception("Failed to connect to InfluxDB after maximum retries")


def find_rrd_files(data_dir):
    """Find all RRD files in the Smokeping data directory."""
    rrd_files = []
    data_path = Path(data_dir)

    if not data_path.exists():
        logger.warning(f"Smokeping data directory not found: {data_dir}")
        return rrd_files

    for rrd_file in data_path.rglob('*.rrd'):
        relative_path = rrd_file.relative_to(data_path)
        parts = list(relative_path.parts)
        if len(parts) >= 1:
            target_name = '/'.join(parts)[:-4]  # Remove .rrd
            rrd_files.append({
                'path': str(rrd_file),
                'target': target_name
            })

    return rrd_files


def parse_rrd_data(rrd_file):
    """Parse RRD file using rrdtool and return latest values."""
    try:
        result = subprocess.run(
            ['rrdtool', 'fetch', rrd_file, 'AVERAGE', '-s', '-300'],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            logger.debug(f"rrdtool fetch failed for {rrd_file}: {result.stderr}")
            return None

        lines = result.stdout.strip().split('\n')

        if len(lines) < 3:
            return None

        # Get the last non-nan line (skip header lines)
        for line in reversed(lines[2:]):
            if ':' not in line:
                continue

            parts = line.split(':')
            if len(parts) != 2:
                continue

            timestamp_str = parts[0].strip()
            values_str = parts[1].strip()

            if not values_str:
                continue

            values = values_str.split()
            if len(values) < 3:
                continue

            try:
                # Smokeping RRD columns: uptime(0), loss(1), median(2), ping1-20(3-22)
                loss_str = values[1].lower()
                median_str = values[2].lower()

                # Skip lines where loss and median are both nan
                if loss_str == 'nan' and median_str == 'nan':
                    continue

                loss = float(values[1]) if loss_str != 'nan' else 0
                median = float(values[2]) if median_str != 'nan' else None

                # Skip if we don't have a valid median (latency)
                if median is None:
                    continue

                # Convert median from seconds to milliseconds
                latency_ms = median * 1000

                # Loss is already a ratio (0-1), convert to percentage
                loss_percent = loss * 100 if loss <= 1 else loss

                return {
                    'timestamp': int(timestamp_str),
                    'loss_percent': round(loss_percent, 2),
                    'latency_ms': round(latency_ms, 3)
                }
            except (ValueError, IndexError) as e:
                logger.debug(f"Failed to parse values: {e}")
                continue

        return None

    except subprocess.TimeoutExpired:
        logger.warning(f"rrdtool timeout for {rrd_file}")
        return None
    except FileNotFoundError:
        logger.error("rrdtool not found - is it installed?")
        return None
    except Exception as e:
        logger.debug(f"Error parsing RRD {rrd_file}: {e}")
        return None


def parse_smokeping_latest(data_dir):
    """Parse Smokeping RRD files and extract metrics."""
    results = []

    for rrd_info in find_rrd_files(data_dir):
        data = parse_rrd_data(rrd_info['path'])
        if data and data.get('latency_ms') is not None:
            results.append({
                'target': rrd_info['target'],
                'latency_ms': data['latency_ms'],
                'loss_percent': data['loss_percent']
            })

    return results


def write_metrics_to_influx(client, metrics):
    """Write Smokeping metrics to InfluxDB."""
    if not metrics:
        return 0

    json_body = []
    timestamp = datetime.utcnow().isoformat() + "Z"

    for metric in metrics:
        target_parts = metric['target'].split('/')
        category = target_parts[0] if target_parts else 'Unknown'
        target_name = target_parts[-1] if target_parts else metric['target']

        point = {
            "measurement": "smokeping",
            "tags": {
                "target": target_name,
                "category": category,
                "full_path": metric['target']
            },
            "time": timestamp,
            "fields": {
                "latency_ms": float(metric['latency_ms']),
                "loss_percent": float(metric['loss_percent'])
            }
        }
        json_body.append(point)

    try:
        client.write_points(json_body)
        return len(json_body)
    except Exception as e:
        logger.error(f"Failed to write to InfluxDB: {e}")
        return 0


def main():
    """Main export loop."""
    logger.info(f"Smokeping Exporter starting - data dir: {SMOKEPING_DATA_DIR}, interval: {EXPORT_INTERVAL}s")

    # Wait for Smokeping and InfluxDB to be ready
    logger.info("Waiting 60s for services to initialize...")
    time.sleep(60)

    client = get_influx_client()

    logger.info("Starting export loop...")

    while True:
        try:
            rrd_files = find_rrd_files(SMOKEPING_DATA_DIR)
            if not rrd_files:
                logger.info(f"No RRD files found in {SMOKEPING_DATA_DIR}, waiting...")
            else:
                logger.debug(f"Found {len(rrd_files)} RRD files")
                metrics = parse_smokeping_latest(SMOKEPING_DATA_DIR)
                count = write_metrics_to_influx(client, metrics)

                if count > 0:
                    logger.info(f"Exported {count} Smokeping metrics to InfluxDB")
                else:
                    logger.info("No valid metrics to export (RRD data may not be ready yet)")

        except Exception as e:
            logger.error(f"Error in export cycle: {e}")
            try:
                client = get_influx_client()
            except Exception:
                pass

        time.sleep(EXPORT_INTERVAL)


if __name__ == '__main__':
    main()
