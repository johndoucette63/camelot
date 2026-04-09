#!/bin/bash
# Benchmark Ollama LLM performance on HOLYGRAIL
# Usage: bash scripts/benchmark-ollama.sh [host]
#   Default host: 192.168.10.129

set -euo pipefail

HOST="${1:-192.168.10.129}"
BASE_URL="http://$HOST:11434"
MODEL="llama3.1:8b"

echo "=== Ollama Benchmark ==="
echo "Host: $BASE_URL"
echo "Model: $MODEL"
echo "Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo ""

# Check Ollama is reachable
if ! curl -sf "$BASE_URL/" >/dev/null 2>&1; then
    echo "ERROR: Ollama not reachable at $BASE_URL"
    exit 1
fi

benchmark_prompt() {
    local label="$1"
    local prompt="$2"

    echo "--- $label ---"
    local start_time
    start_time=$(python3 -c 'import time; print(time.time())')

    local response
    response=$(curl -sf "$BASE_URL/api/generate" \
        -d "{\"model\":\"$MODEL\",\"prompt\":$(python3 -c "import json; print(json.dumps('''$prompt'''))"),\"stream\":false}" \
        2>/dev/null)

    local end_time
    end_time=$(python3 -c 'import time; print(time.time())')

    if [ -z "$response" ]; then
        echo "  ERROR: No response"
        return 1
    fi

    # Parse metrics from Ollama response
    python3 -c "
import json, sys
r = json.loads('''$response''')
wall_time = $end_time - $start_time

# Prompt eval
prompt_tokens = r.get('prompt_eval_count', 0)
prompt_ns = r.get('prompt_eval_duration', 1)
prompt_tps = prompt_tokens / (prompt_ns / 1e9) if prompt_ns > 0 else 0

# Generation
gen_tokens = r.get('eval_count', 0)
gen_ns = r.get('eval_duration', 1)
gen_tps = gen_tokens / (gen_ns / 1e9) if gen_ns > 0 else 0

print(f'  Prompt tokens: {prompt_tokens}')
print(f'  Generated tokens: {gen_tokens}')
print(f'  Prompt eval: {prompt_tps:.1f} tokens/sec')
print(f'  Generation: {gen_tps:.1f} tokens/sec')
print(f'  Wall-clock: {wall_time:.1f}s')
print(f'  Total duration: {r.get(\"total_duration\", 0)/1e9:.1f}s')
" 2>/dev/null || echo "  ERROR: Could not parse response metrics"
    echo ""
}

# Short prompt (~20 words)
benchmark_prompt "Short Prompt (~20 words)" \
    "What is a reverse proxy and why would someone use one?"

# Medium prompt (~200 words)
benchmark_prompt "Medium Prompt (~200 words)" \
    "I have a home network with several devices: a NAS server running OpenMediaVault with Samba shares for movies, TV shows, and music. A Raspberry Pi running Deluge for torrents with a VPN kill-switch. Another Pi running Pi-hole for DNS ad blocking. A central server running Plex for media streaming with GPU-accelerated transcoding, Grafana and InfluxDB for monitoring, Smokeping for latency tracking, and Traefik as a reverse proxy. All devices are on a 192.168.10.0/24 subnet. The monitoring stack collects latency data to 40+ targets every 5 minutes and runs speedtests every 30 minutes. I want you to analyze this setup and suggest three specific improvements that would make the network more reliable and easier to manage. Focus on practical changes, not theoretical best practices."

# Advisor-length prompt (~500 words)
benchmark_prompt "Advisor Prompt (~500 words)" \
    "You are a network infrastructure advisor for a home lab called Camelot. Here is the current state of the network. The central server HOLYGRAIL runs Ubuntu 24.04 with an AMD Ryzen 7800X3D, 32GB DDR5 RAM, and an NVIDIA RTX 2070 Super GPU. It hosts Plex with hardware transcoding, a full monitoring stack with Grafana dashboards showing network latency and speedtest data, InfluxDB for time-series storage, Smokeping monitoring 40+ network targets, Traefik reverse proxy providing clean hostname routing, and Portainer for container management. The Torrentbox is a Raspberry Pi 5 running Deluge with a PIA VPN kill-switch, along with Sonarr, Radarr, Prowlarr, Lidarr, LazyLibrarian, and FlareSolverr. The NAS is a Raspberry Pi 4 running OpenMediaVault with 4.6TB of media storage shared via Samba. A separate Pi 5 runs Pi-hole DNS. The Mac workstation is used for development and management only. Current issues observed in monitoring: occasional latency spikes to the NAS during large Plex library scans, the Torrentbox showing elevated CPU when all arr apps run import scans simultaneously, and 9 devices on the network consistently showing latency above 200ms. Recent changes include migrating Plex from the Pi to HOLYGRAIL for GPU transcoding, deploying the monitoring stack on HOLYGRAIL, and setting up Traefik for hostname-based routing. Please provide a comprehensive analysis of this network with specific recommendations for the next improvements. Consider the monitoring data patterns, identify the root causes of the observed issues, suggest optimizations for the torrent workflow, and recommend what the next infrastructure project should be. Be specific with commands, configuration changes, and expected outcomes."

# VRAM usage
echo "=== GPU Memory Usage ==="
ssh john@holygrail "nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv,noheader" 2>/dev/null || \
    echo "  Could not query GPU (SSH not available or nvidia-smi failed)"

echo ""
echo "=== Benchmark Complete ==="
