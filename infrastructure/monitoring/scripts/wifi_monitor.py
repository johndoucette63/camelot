#!/usr/bin/env python3
"""
WiFi Channel Monitor
Scans for nearby networks and logs congestion metrics to InfluxDB
Also attempts to identify which band devices are using based on latency patterns
"""

import os
import time
import logging
import subprocess
import re
from datetime import datetime
from influxdb import InfluxDBClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
INFLUXDB_HOST = os.getenv('INFLUXDB_HOST', 'localhost')
INFLUXDB_PORT = int(os.getenv('INFLUXDB_PORT', 8086))
INFLUXDB_DB = os.getenv('INFLUXDB_DB', 'network_metrics')
INFLUXDB_USER = os.getenv('INFLUXDB_USER', 'grafana')
INFLUXDB_PASSWORD = os.getenv('INFLUXDB_PASSWORD', 'grafanapass')
WIFI_INTERFACE = os.getenv('WIFI_INTERFACE', 'wlan0')
SCAN_INTERVAL = int(os.getenv('SCAN_INTERVAL', 300))  # 5 minutes default

# 2.4GHz non-overlapping channels
CHANNELS_24GHZ = list(range(1, 14))
CHANNELS_5GHZ = [36, 40, 44, 48, 52, 56, 60, 64, 100, 104, 108, 112, 116, 120, 124, 128, 132, 136, 140, 144, 149, 153, 157, 161, 165]


def get_influx_client():
    """Create InfluxDB client."""
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
        logger.error(f"Failed to connect to InfluxDB: {e}")
        return None


def scan_wifi():
    """Scan for nearby WiFi networks."""
    networks = []

    try:
        # Run iwlist scan (requires sudo)
        result = subprocess.run(
            ['sudo', 'iwlist', WIFI_INTERFACE, 'scan'],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            logger.error(f"WiFi scan failed: {result.stderr}")
            return networks

        output = result.stdout

        # Parse the output
        current_network = {}

        for line in output.split('\n'):
            line = line.strip()

            if 'Cell' in line and 'Address:' in line:
                # Save previous network
                if current_network and 'essid' in current_network:
                    networks.append(current_network)
                # Start new network
                mac = line.split('Address:')[1].strip()
                current_network = {'mac': mac}

            elif 'Channel:' in line:
                try:
                    channel = int(line.split(':')[1])
                    current_network['channel'] = channel
                    # Determine band
                    if channel <= 14:
                        current_network['band'] = '2.4GHz'
                    else:
                        current_network['band'] = '5GHz'
                except (ValueError, IndexError):
                    pass

            elif 'Signal level=' in line:
                try:
                    # Extract signal level in dBm
                    match = re.search(r'Signal level[=:](-?\d+)', line)
                    if match:
                        current_network['signal_dbm'] = int(match.group(1))
                except (ValueError, IndexError):
                    pass

            elif 'ESSID:' in line:
                try:
                    essid = line.split('ESSID:')[1].strip().strip('"')
                    current_network['essid'] = essid if essid else '(hidden)'
                except IndexError:
                    current_network['essid'] = '(hidden)'

        # Don't forget the last network
        if current_network and 'essid' in current_network:
            networks.append(current_network)

    except subprocess.TimeoutExpired:
        logger.error("WiFi scan timed out")
    except Exception as e:
        logger.error(f"Error scanning WiFi: {e}")

    return networks


def calculate_channel_congestion(networks):
    """Calculate congestion metrics per channel."""
    channel_data = {}

    for network in networks:
        channel = network.get('channel')
        if channel is None:
            continue

        if channel not in channel_data:
            channel_data[channel] = {
                'count': 0,
                'signals': [],
                'band': network.get('band', 'unknown'),
                'networks': []
            }

        channel_data[channel]['count'] += 1
        if 'signal_dbm' in network:
            channel_data[channel]['signals'].append(network['signal_dbm'])
        channel_data[channel]['networks'].append(network.get('essid', 'unknown'))

    # Calculate averages and interference score
    for channel, data in channel_data.items():
        if data['signals']:
            data['avg_signal'] = sum(data['signals']) / len(data['signals'])
            data['max_signal'] = max(data['signals'])
            # Interference score: more networks + stronger signals = worse
            # Score from 0-100, higher = more congested
            data['interference_score'] = min(100, data['count'] * 15 + (100 + data['max_signal']))
        else:
            data['avg_signal'] = -100
            data['max_signal'] = -100
            data['interference_score'] = data['count'] * 10

    return channel_data


def write_wifi_metrics(client, networks, channel_data):
    """Write WiFi metrics to InfluxDB."""
    if not client:
        return

    timestamp = datetime.utcnow().isoformat() + "Z"
    json_body = []

    # Write per-channel congestion data
    for channel, data in channel_data.items():
        point = {
            "measurement": "wifi_channel",
            "tags": {
                "channel": str(channel),
                "band": data['band']
            },
            "time": timestamp,
            "fields": {
                "network_count": data['count'],
                "avg_signal_dbm": float(data['avg_signal']),
                "max_signal_dbm": float(data['max_signal']),
                "interference_score": float(data['interference_score'])
            }
        }
        json_body.append(point)

    # Write summary metrics
    networks_24ghz = sum(1 for n in networks if n.get('band') == '2.4GHz')
    networks_5ghz = sum(1 for n in networks if n.get('band') == '5GHz')

    # Find most and least congested 2.4GHz channels
    channels_24 = {ch: d for ch, d in channel_data.items() if d['band'] == '2.4GHz'}
    if channels_24:
        most_congested_24 = max(channels_24.items(), key=lambda x: x[1]['interference_score'])
        least_congested_24 = min(channels_24.items(), key=lambda x: x[1]['interference_score'])
    else:
        most_congested_24 = (0, {'interference_score': 0})
        least_congested_24 = (0, {'interference_score': 0})

    summary_point = {
        "measurement": "wifi_summary",
        "tags": {},
        "time": timestamp,
        "fields": {
            "total_networks": len(networks),
            "networks_24ghz": networks_24ghz,
            "networks_5ghz": networks_5ghz,
            "channels_in_use": len(channel_data),
            "most_congested_channel": most_congested_24[0],
            "most_congested_score": float(most_congested_24[1]['interference_score']),
            "least_congested_channel": least_congested_24[0],
            "least_congested_score": float(least_congested_24[1]['interference_score'])
        }
    }
    json_body.append(summary_point)

    try:
        client.write_points(json_body)
        logger.info(f"Wrote WiFi metrics: {len(networks)} networks, {len(channel_data)} channels")
    except Exception as e:
        logger.error(f"Failed to write to InfluxDB: {e}")


def print_congestion_report(networks, channel_data):
    """Print a human-readable congestion report."""
    print("\n" + "=" * 60)
    print("WiFi Congestion Report")
    print("=" * 60)

    # 2.4GHz channels
    print("\n2.4GHz Band:")
    print("-" * 40)
    channels_24 = sorted([(ch, d) for ch, d in channel_data.items() if d['band'] == '2.4GHz'],
                         key=lambda x: x[1]['interference_score'], reverse=True)

    for channel, data in channels_24:
        bar = "█" * min(20, int(data['interference_score'] / 5))
        status = "CONGESTED" if data['interference_score'] > 50 else "OK"
        print(f"  Ch {channel:2d}: {bar:20s} {data['interference_score']:5.1f} ({data['count']} networks) [{status}]")
        for essid in data['networks'][:3]:
            print(f"         └─ {essid}")
        if len(data['networks']) > 3:
            print(f"         └─ ... and {len(data['networks']) - 3} more")

    # 5GHz channels
    print("\n5GHz Band:")
    print("-" * 40)
    channels_5 = sorted([(ch, d) for ch, d in channel_data.items() if d['band'] == '5GHz'],
                        key=lambda x: x[0])

    if channels_5:
        for channel, data in channels_5:
            bar = "█" * min(20, int(data['interference_score'] / 5))
            print(f"  Ch {channel:3d}: {bar:20s} {data['interference_score']:5.1f} ({data['count']} networks)")
    else:
        print("  No 5GHz networks detected (may need 5GHz capable interface)")

    # Recommendations
    print("\nRecommendations:")
    print("-" * 40)

    # Find best 2.4GHz channel (1, 6, or 11 only - non-overlapping)
    non_overlapping = [1, 6, 11]
    best_channel = None
    best_score = float('inf')

    for ch in non_overlapping:
        if ch in channel_data:
            if channel_data[ch]['interference_score'] < best_score:
                best_score = channel_data[ch]['interference_score']
                best_channel = ch
        else:
            # Channel not in use at all - best choice
            best_channel = ch
            best_score = 0
            break

    if best_channel:
        print(f"  • Best 2.4GHz channel: {best_channel} (score: {best_score:.1f})")

    # Check for self-interference
    own_networks = [n for n in networks if 'camelot' in n.get('essid', '').lower() or
                   'peasants' in n.get('essid', '').lower() or
                   'shrubbery' in n.get('essid', '').lower() or
                   'rabbit' in n.get('essid', '').lower()]

    own_channels = set(n.get('channel') for n in own_networks if n.get('channel'))
    overlapping_own = [ch for ch in own_channels if ch not in [1, 6, 11] and ch <= 14]

    if overlapping_own:
        print(f"  • WARNING: Your networks use overlapping channels: {overlapping_own}")
        print(f"    Move to channels 1, 6, or 11 only!")

    if len(own_channels & {1, 6, 11}) > 1:
        print(f"  • Your networks span multiple non-overlapping channels: {own_channels & {1, 6, 11}}")

    print("=" * 60 + "\n")


def main():
    """Main monitoring loop."""
    logger.info(f"WiFi Monitor starting - interface: {WIFI_INTERFACE}, interval: {SCAN_INTERVAL}s")

    client = get_influx_client()

    while True:
        try:
            logger.info("Scanning WiFi networks...")
            networks = scan_wifi()

            if networks:
                channel_data = calculate_channel_congestion(networks)
                write_wifi_metrics(client, networks, channel_data)
                print_congestion_report(networks, channel_data)
            else:
                logger.warning("No networks found in scan")

        except Exception as e:
            logger.error(f"Error in monitoring loop: {e}")

        time.sleep(SCAN_INTERVAL)


if __name__ == '__main__':
    # If run with --once flag, just do one scan and exit
    import sys
    if '--once' in sys.argv:
        networks = scan_wifi()
        if networks:
            channel_data = calculate_channel_congestion(networks)
            print_congestion_report(networks, channel_data)

            client = get_influx_client()
            if client:
                write_wifi_metrics(client, networks, channel_data)
        else:
            print("No networks found")
    else:
        main()
