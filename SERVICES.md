# Camelot Services

Active web interfaces running on HOLYGRAIL (`192.168.10.129`).  
All `*.holygrail` hostnames require the SSH config or local DNS (Pi-hole) to resolve.

| Service | URL | Description |
|---------|-----|-------------|
| Network Advisor | [advisor.holygrail](http://advisor.holygrail) | Device inventory & AI network advisor (F4.x) |
| Plex | [plex.holygrail](http://plex.holygrail) | Media server (NVENC transcoding) |
| Ollama | [ollama.holygrail](http://ollama.holygrail) | Local LLM API (Llama 3.1 8B, GPU-accelerated) |
| Grafana | [grafana.holygrail](http://grafana.holygrail) | Monitoring dashboards (InfluxDB + Smokeping data) |
| Smokeping | [smokeping.holygrail](http://smokeping.holygrail) | Network latency & packet loss graphs |
| Portainer | [portainer.holygrail](http://portainer.holygrail) | Docker container management UI |
| Traefik | [traefik.holygrail](http://traefik.holygrail) | Reverse proxy dashboard |

## Other Device Interfaces

| Service | URL | Description |
|---------|-----|-------------|
| Pi-hole | [http://192.168.10.150/admin](http://192.168.10.150/admin) | DNS ad-blocking admin (Pi-hole DNS, `.150`) |
