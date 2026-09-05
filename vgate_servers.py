#!/usr/bin/env python3
"""
VPN Gate Server List Updater - Enhanced Version
Fetches latest VPN Gate servers and outputs servers.json with full configs
GitHub: kaleed-stvpn/vgate_servers.py
Output: kaleed-stvpn/output/servers.json
"""

import json
import base64
import requests
import re
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import os
import sys

VPN_GATE_API_URL = "https://www.vpngate.net/api/iphone/"
OUTPUT_DIR = "output"
OUTPUT_FILE = "servers.json"
MAX_SERVERS = 10  # အကောင်းဆုံး ဆာဗာ ၁၀ ခုသာ ထုတ်ယူမည်

def parse_config_from_base64(base64_config: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Base64 config ကနေ OpenVPN ဆက်တင်တွေကို ခွဲထုတ်ပါ
    """
    try:
        config_text = base64.b64decode(base64_config).decode('utf-8', errors='ignore')
        
        # အရေးကြီးဆုံး လိုအပ်ချက်တွေကို extract လုပ်ပါ
        # 1. remote (server IP/Port)
        remote_match = re.search(r'^remote\s+([^\s]+)\s+([^\s]+)', config_text, re.MULTILINE)
        if remote_match:
            server_ip = remote_match.group(1)
            server_port = remote_match.group(2)
        else:
            server_ip, server_port = None, None
        
        # 2. Protocol (proto)
        proto_match = re.search(r'^proto\s+(\w+)', config_text, re.MULTILINE)
        protocol = proto_match.group(1) if proto_match else None
        
        # 3. Username/Password (auth-user-pass)
        auth_match = re.search(r'^auth-user-pass\s*(\S+)?', config_text, re.MULTILINE)
        username = "vpn"  # VPN Gate ရဲ့ default
        password = "vpn"
        
        # 4. CA Certificate
        ca_match = re.search(r'<ca>\s*(.+?)\s*</ca>', config_text, re.DOTALL)
        ca_cert = ca_match.group(1).strip() if ca_match else None
        
        # 5. Client Certificate
        cert_match = re.search(r'<cert>\s*(.+?)\s*</cert>', config_text, re.DOTALL)
        client_cert = cert_match.group(1).strip() if cert_match else None
        
        # 6. Client Key
        key_match = re.search(r'<key>\s*(.+?)\s*</key>', config_text, re.DOTALL)
        client_key = key_match.group(1).strip() if key_match else None
        
        return {
            "config_text": config_text,
            "server_ip": server_ip,
            "server_port": server_port,
            "protocol": protocol,
            "ca_cert": ca_cert,
            "client_cert": client_cert,
            "client_key": client_key,
            "username": username,
            "password": password
        }
        
    except Exception as e:
        print(f"⚠️ Config parsing error: {e}")
        return None

def is_server_active(server: Dict) -> bool:
    """
    ဆာဗာတစ်ခု အသက်ဝင်ပြီး အသုံးပြုနိုင်မလား စစ်ဆေးပါ
    """
    try:
        # Null/Empty values တွေကို ကာကွယ်ရန်
        sessions = int(server.get("sessions", 0) or 0)
        score = int(server.get("score", 0) or 0)
        speed = int(server.get("speed", 0) or 0)
        ping = int(server.get("ping", 999) or 999)
        uptime = int(server.get("uptime", 0) or 0)
        
        # အသက်ဝင်မှုသတ်မှတ်ချက် (ယခင်ထက် ပိုမိုပျော့ပြောင်းအောင် ပြင်ဆင်)
        is_active = (
            sessions >= 0 and           # Active users (0 ဖြစ်နိုင်တယ်)
            score > 5 and               # အနည်းဆုံး score
            speed > 10000 and           # အနည်းဆုံး 10 Kbps
            ping < 500 and              # Ping 500ms အောက်
            uptime > 600                # အနည်းဆုံး 10 မိနစ် run ထားတယ်
        )
        
        return is_active
        
    except (ValueError, TypeError):
        return False

def get_quality_score(server: Dict) -> int:
    """
    အရည်အသွေးအမှတ်ကို တွက်ချက်ပါ (အမြင့်ဆုံးက အကောင်းဆုံး)
    """
    try:
        score = int(server.get("score", 0) or 0)
        speed = int(server.get("speed", 0) or 0)
        ping = int(server.get("ping", 999) or 999)
        sessions = int(server.get("sessions", 0) or 0)
        uptime = int(server.get("uptime", 0) or 0)
        
        # ပိုမိုကောင်းမွန်တဲ့ Quality Score တွက်နည်း
        quality = (
            (score * 2) +               # Score ကို အဓိကထား
            (speed / 100000) -          # Speed bonus
            (ping * 2) -                # Ping penalty
            (sessions / 20) +           # Sessions များလွန်းရင် penalty
            (uptime / 3600)             # Uptime bonus (hours)
        )
        
        return int(quality)
        
    except (ValueError, TypeError):
        return 0

def fetch_vpn_gate_servers() -> Optional[List[Dict]]:
    """
    VPN Gate API ကနေ ဆာဗာစာရင်းကို ရယူပါ
    """
    try:
        print("🔄 VPN Gate ဆာဗာများကို ရယူနေပါသည်...")
        response = requests.get(VPN_GATE_API_URL, timeout=30)
        response.raise_for_status()
        
        lines = response.text.strip().split('\n')
        servers = []
        
        # Header စာကြောင်းကို ကျော်ပါ (# နဲ့စတယ်)
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
                
                # config_base64 ရှိမှသာ ထည့်ပါ
                if server["config_base64"]:
                    try:
                        # Base64 မှန်ကန်မှုကို စစ်ဆေးပါ
                        decoded = base64.b64decode(server["config_base64"])
                        if len(decoded) > 100:
                            servers.append(server)
                    except Exception:
                        continue
                        
            except (ValueError, IndexError) as e:
                continue
                
        return servers
        
    except requests.RequestException as e:
        print(f"❌ VPN Gate ဒေတာရယူရာတွင် အမှားရှိသည်: {e}")
        return None

def create_output_dir():
    """ထွက်ရှိမည့် ဖိုင်တွဲကို ဖန်တီးပါ"""
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"📁 ထွက်ရှိမည့်ဖိုင်တွဲကို ဖန်တီးပြီး: {OUTPUT_DIR}")

def main():
    """အဓိက အလုပ်လုပ်ဆောင်ချက်"""
    create_output_dir()
    
    # ဆာဗာစာရင်းကို ရယူပါ
    servers = fetch_vpn_gate_servers()
    
    if servers is None:
        print("❌ ဆာဗာစာရင်းရယူရန် မအောင်မြင်ပါ")
        sys.exit(1)
    
    print(f"📡 စုစုပေါင်းဆာဗာ {len(servers)} ခုတွေ့ရှိပါသည်")
    
    # Active ဆာဗာများကို စစ်ထုတ်ပါ
    active_servers = []
    inactive_count = 0
    
    for server in servers:
        # Config ကို parse လုပ်ပါ
        parsed_config = parse_config_from_base64(server["config_base64"])
        if parsed_config is None:
            inactive_count += 1
            continue
            
        # Config ထဲက အချက်အလက်တွေကို server dict ထဲထည့်ပါ
        server["config_text"] = parsed_config["config_text"]
        server["config_content"] = parsed_config  # Full config object
        server["ca_cert"] = parsed_config["ca_cert"]
        server["client_cert"] = parsed_config["client_cert"]
        server["client_key"] = parsed_config["client_key"]
        server["username"] = parsed_config["username"]
        server["password"] = parsed_config["password"]
        
        # Config ထဲက IP/Port ကို သုံးပါ (မရှိရင် API ကနေယူပါ)
        if parsed_config["server_ip"]:
            server["ip"] = parsed_config["server_ip"]
        if parsed_config["server_port"]:
            server["port"] = parsed_config["server_port"]
        else:
            server["port"] = "1194"  # OpenVPN default port
            
        if parsed_config["protocol"]:
            server["protocol"] = parsed_config["protocol"]
        else:
            server["protocol"] = "udp"
        
        # Active ဆာဗာလား စစ်ဆေးပါ
        if is_server_active(server):
            server["quality_score"] = get_quality_score(server)
            server["is_active"] = True
            active_servers.append(server)
        else:
            inactive_count += 1
    
    print(f"✅ Active ဆာဗာ: {len(active_servers)}")
    print(f"⏸️  Inactive ဆာဗာ: {inactive_count}")
    
    # Quality Score အတိုင်း စီပါ (အမြင့်ဆုံးက အကောင်းဆုံး)
    active_servers.sort(key=lambda x: x["quality_score"], reverse=True)
    
    # အကောင်းဆုံး ဆာဗာ MAX_SERVERS ခုကိုသာ ရွေးပါ
    top_servers = active_servers[:MAX_SERVERS]
    
    # JSON output အတွက် ပြင်ဆင်ပါ
    output_data = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "total_servers": len(servers),
        "active_servers": len(active_servers),
        "selected_servers": len(top_servers),
        "servers": top_servers
    }
    
    # JSON ဖိုင်သို့ သိမ်းပါ
    output_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        print(f"💾 အကောင်းဆုံးဆာဗာ {len(top_servers)} ခုကို သိမ်းဆည်းပြီး: {output_path}")
    except Exception as e:
        print(f"❌ ဖိုင်သိမ်းဆည်းရာတွင် အမှားရှိသည်: {e}")
        sys.exit(1)
    
    # အကောင်းဆုံး ဆာဗာ ၅ ခုကို ပြသပါ
    print("\n🏆 အကောင်းဆုံး Active ဆာဗာ ၅ ခု:")
    print("-" * 70)
    for i, server in enumerate(top_servers[:5], 1):
        flag = server["country_code"].upper()
        print(f"{i}. {server.get('hostname', 'Unknown')}")
        print(f"   🌍 {server.get('country', 'Unknown')} ({flag})")
        print(f"   📍 IP: {server.get('ip', 'N/A')}:{server.get('port', 'N/A')} ({server.get('protocol', 'N/A')})")
        print(f"   👥 Sessions: {server.get('sessions', 0)}")
        print(f"   ⚡ Speed: {server.get('speed', 0):,} bps")
        print(f"   📊 Quality: {server.get('quality_score', 0)}")
        print(f"   🏷️  Score: {server.get('score', 0)}")
        print(f"   🔐 Config: {'Yes' if server.get('config_content') else 'No'}")
        print("-" * 70)
    
    print(f"\n✅ အပြည့်အစုံ ပြီးဆုံးပါပြီ။ အချိန်: {datetime.utcnow().isoformat()}Z")

if __name__ == "__main__":
    main()
