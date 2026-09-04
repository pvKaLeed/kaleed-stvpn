#!/usr/bin/env python3
"""
VPN Gate Server List Updater
Fetches latest VPN Gate servers and outputs servers.json
GitHub: kaleed-stvpn/vgate_servers.py
Output: kaleed-stvpn/output/servers.json
"""

import json
import base64
import requests
from datetime import datetime
from typing import List, Dict, Optional
import os
import sys

VPN_GATE_API_URL = "https://www.vpngate.net/api/iphone/"
OUTPUT_DIR = "output"
OUTPUT_FILE = "servers.json"


def is_server_active(server: Dict) -> bool:
    """
    Check if a server is likely active and usable.
    Uses multiple metrics to determine server quality.
    """
    try:
        sessions = int(server.get("sessions", 0))
        score = int(server.get("score", 0))
        speed = int(server.get("speed", 0))
        ping = int(server.get("ping", 999))
        uptime = int(server.get("uptime", 0))
        
        # Active server criteria:
        # 1. Has at least 1 active session (or was recently used)
        # 2. Score is reasonable
        # 3. Not extremely slow
        # 4. Ping is reasonable
        # 5. Has been running for at least some time
        
        is_active = (
            sessions > 0 and           # Has active users
            score > 10 and              # Reasonable score
            speed > 10000 and           # At least 10 Kbps
            ping < 500 and              # Ping under 500ms
            uptime > 3600               # Running for at least 1 hour
        )
        
        return is_active
        
    except (ValueError, TypeError):
        return False


def get_quality_score(server: Dict) -> int:
    """
    Calculate quality score for sorting (higher is better)
    """
    try:
        score = int(server.get("score", 0))
        speed = int(server.get("speed", 0))
        ping = int(server.get("ping", 999))
        sessions = int(server.get("sessions", 0))
        uptime = int(server.get("uptime", 0))
        
        # Higher score is better
        # Speed bonus: higher speed = better
        # Ping penalty: lower ping = better
        # Session penalty: too many users = slower
        # Uptime bonus: longer uptime = more reliable
        
        quality = (
            score +
            (speed / 100000) -           # Speed bonus
            (ping * 2) -                 # Ping penalty
            (sessions / 10) +            # Session penalty
            (uptime / 3600)              # Uptime bonus (hours)
        )
        
        return int(quality)
        
    except (ValueError, TypeError):
        return 0


def fetch_vpn_gate_servers() -> Optional[List[Dict]]:
    """
    Fetch VPN Gate server list from API
    Returns list of server dictionaries or None if failed
    """
    try:
        print("🔄 Fetching VPN Gate servers...")
        response = requests.get(VPN_GATE_API_URL, timeout=30)
        response.raise_for_status()
        
        lines = response.text.strip().split('\n')
        servers = []
        
        # Skip header line (starts with #)
        for line in lines[1:]:
            if not line.strip():
                continue
                
            parts = line.split(',')
            if len(parts) < 15:
                continue
                
            try:
                server = {
                    "hostname": parts[0].strip(),
                    "ip": parts[1].strip(),
                    "score": int(parts[2].strip()) if parts[2].strip() else 0,
                    "ping": int(parts[3].strip()) if parts[3].strip() else 999,
                    "speed": int(parts[4].strip()) if parts[4].strip() else 0,
                    "country": parts[5].strip(),
                    "country_code": parts[6].strip(),
                    "sessions": int(parts[7].strip()) if parts[7].strip() else 0,
                    "uptime": int(parts[8].strip()) if parts[8].strip() else 0,
                    "total_users": int(parts[9].strip()) if parts[9].strip() else 0,
                    "total_traffic": int(parts[10].strip()) if parts[10].strip() else 0,
                    "log_type": parts[11].strip() if len(parts) > 11 else "",
                    "operator": parts[12].strip() if len(parts) > 12 else "",
                    "message": parts[13].strip() if len(parts) > 13 else "",
                    "config_base64": parts[14].strip() if len(parts) > 14 else ""
                }
                
                # Only add if config_base64 is valid and not empty
                if server["config_base64"]:
                    try:
                        # Verify base64 is valid
                        decoded = base64.b64decode(server["config_base64"])
                        if len(decoded) > 100:  # Must be reasonable config length
                            servers.append(server)
                    except Exception:
                        continue
                        
            except (ValueError, IndexError) as e:
                continue
                
        return servers
        
    except requests.RequestException as e:
        print(f"❌ Error fetching VPN Gate data: {e}")
        return None


def create_output_dir():
    """Create output directory if it doesn't exist"""
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"📁 Created output directory: {OUTPUT_DIR}")


def main():
    """Main entry point"""
    # Create output directory
    create_output_dir()
    
    # Fetch servers
    servers = fetch_vpn_gate_servers()
    
    if servers is None:
        print("❌ Failed to fetch server list")
        sys.exit(1)
    
    print(f"📡 Found {len(servers)} total servers")
    
    # Filter active servers
    active_servers = []
    inactive_count = 0
    
    for server in servers:
        if is_server_active(server):
            # Add quality score
            server["quality_score"] = get_quality_score(server)
            server["is_active"] = True
            active_servers.append(server)
        else:
            inactive_count += 1
    
    print(f"✅ Active servers: {len(active_servers)}")
    print(f"⏸️  Inactive servers: {inactive_count}")
    
    # Sort by quality score (highest first)
    active_servers.sort(key=lambda x: x["quality_score"], reverse=True)
    
    # Prepare output data
    output_data = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "total_servers": len(servers),
        "active_servers": len(active_servers),
        "servers": active_servers
    }
    
    # Write to file
    output_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        print(f"💾 Saved {len(active_servers)} active servers to: {output_path}")
    except Exception as e:
        print(f"❌ Error saving file: {e}")
        sys.exit(1)
    
    # Show top 5 servers
    print("\n🏆 Top 5 Active Servers:")
    print("-" * 60)
    for i, server in enumerate(active_servers[:5], 1):
        flag = server["country_code"].upper()
        print(f"{i}. {server['hostname']}")
        print(f"   🌍 {server['country']} ({flag})")
        print(f"   📍 IP: {server['ip']}")
        print(f"   👥 Users: {server['sessions']}")
        print(f"   ⚡ Speed: {server['speed']:,} bps")
        print(f"   📊 Quality: {server['quality_score']}")
        print(f"   🏷️  Score: {server['score']}")
        print("-" * 60)
    
    print(f"\n✅ Update complete at {datetime.utcnow().isoformat()}Z")


if __name__ == "__main__":
    main()
