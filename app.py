from datetime import datetime
from flask import Flask, Response
import requests
import re
import threading
import time
import xml.etree.ElementTree as ET

app = Flask(__name__)

cached_m3u = '#EXTM3U\n'
cached_epg = '<?xml version="1.0" encoding="utf-8"?><tv></tv>'
is_updating = False

def get_dishtv_token():
    signin_url = "https://www.dishtv.in/services/epg/signin"
    headers = {
        "Content-Type": "application/json",
        "Origin": "https://www.dishtv.in",
        "Referer": "https://www.dishtv.in/channel-guide.html"
    }
    try:
        res = requests.post(signin_url, headers=headers, json={}, timeout=5)
        data = res.json()
        if data.get("success") == "true":
            return data.get("token")
    except Exception:
        pass
    return None

def update_background_tasks():
    global cached_m3u, cached_epg, is_updating
    if is_updating:
        return
    is_updating = True
    
    try:
        # ==================== 1. M3U GENERATION LOGIC ====================
        COOKIE_STAR_SPORTS = "https://allinonereborn2.online/jtv-fetch/jstarcookie/cookie.json"
        star_tokens = {}
        try:
            res = requests.get(COOKIE_STAR_SPORTS, timeout=6)
            if res.status_code == 200:
                data = res.json()
                if data and "failed_results" in data:
                    for item in data["failed_results"]:
                        ch_id_str = str(item.get("channel_id"))
                        err_details = item.get("error_details", {})
                        final_url = err_details.get("final_url", "")
                        if "__hdnea__=" in final_url:
                            match = re.search(r'__hdnea__=([^&]+)', final_url)
                            if match:
                                star_tokens[ch_id_str] = f"__hdnea__={match.group(1)}"
        except Exception:
            pass

        token_urls = [
            "https://allinonereborn2.online/jstrweb2/cookies.json",
            "https://allinonereborn2.online/jstrweb3/cookies.json",
            "https://allinonereborn2.online/jstrweb4/cookies.json"
        ]
        global_token = ""
        for url in token_urls:
            try:
                res = requests.get(url, timeout=3)
                if res.status_code == 200:
                    for item in res.json():
                        if isinstance(item, dict) and "cookie" in item:
                            global_token = item["cookie"]
                            break
                    if global_token:
                        break
            except Exception:
                continue

        base_proxy_url = "https://streamflexsmm.in/license/"
        try:
            target_m3u_url = "https://raw.githubusercontent.com/Sflex0719/STBPLUS/main/ZioMobile.m3u"
            res = requests.get(target_m3u_url, timeout=3)
            if res.status_code == 200:
                for line in res.text.splitlines():
                    if 'license_key=' in line:
                        l_key = line.split('license_key=')[1].strip()
                        if l_key and l_key != "null:null":
                            match = re.search(r'(https?://[^\s]+?/)(?:\d+/)?$', l_key)
                            if match:
                                base_proxy_url = match.group(1)
                            else:
                                base_proxy_url = re.sub(r'\d+/?$', '', l_key)
                            break
        except Exception:
            pass

        channels_res = requests.get("https://jjtvxweb.pages.dev/jstr4web.json", timeout=6)
        channels = channels_res.json()
        
        m3u = '#EXTM3U\n'
        regional_langs = ['tamil', 'telugu', 'malayalam', 'marathi', 'bangla', 'kannada', 'gujarati', 'odia']
        
        for ch in channels:
            name = ch.get('name', 'Unknown')
            name_lower = name.lower()
            
            skip = False
            for lang in regional_langs:
                if lang in name_lower:
                    skip = True
                    break
            if skip:
                continue
                
            if " hindi" in name_lower:
                name = re.sub(r'\s+Hindi\b', '', name, flags=re.IGNORECASE)

            url = ch.get('url', '')
            logo = ch.get('logo', '')
            category = ch.get('category', 'Unknown')
            group = f"JioTV+ ▶ | {category}"
            group_logo = "https://i.postimg.cc/52qG6sKt/STREAMXi.png"
            ch_id = str(ch.get('id', ''))
            
            if not url:
                continue
                
            key_id = ch.get('keyId', '')
            key_val = ch.get('key', '')
            has_clearkey = key_id and key_val and key_id != "null" and key_val != "null"
            
            ch_token = star_tokens.get(ch_id) or global_token
            final_url = f"{url}?{ch_token}" if ch_token and '?' not in url else f"{url}&{ch_token}" if ch_token else url
            
            m3u += f'#EXTINF:-1 tvg-id="{ch_id}" group-title="{group}" group-logo="{group_logo}" tvg-logo="{logo}",{name}\n'
            
            if has_clearkey:
                license_key = f"{key_id}:{key_val}"
                m3u += f'#KODIPROP:inputstream.adaptive.license_type=clearkey\n'
                m3u += f'#KODIPROP:inputstream.adaptive.license_key={license_key}\n'
            else:
                custom_license_proxy = f"{base_proxy_url}{ch_id}/"
                m3u += f'#KODIPROP:inputstream.adaptive.license_type=clearkey\n'
                m3u += f'#KODIPROP:inputstream.adaptive.license_key={custom_license_proxy}\n'
                
            m3u += f'#EXTVLCOPT:http-user-agent=plaYtv/7.1.5\n'
            if ch_token:
                m3u += f'#EXTHTTP:{{"cookie":"{ch_token}","Origin":"https://www.jiotv.com/","Referer":"https://www.jiotv.com/"}}\n'
            else:
                m3u += f'#EXTHTTP:{{"Origin":"https://www.jiotv.com/","Referer":"https://www.jiotv.com/"}}\n'
                
            m3u += f'{final_url}\n\n'

        cached_m3u = m3u

        # ==================== 2. EPG GENERATION LOGIC ====================
        token = get_dishtv_token()
        if token:
            channels_url = "https://www.dishtv.in/services/epg/channels"
            epg_headers = {
                "Content-Type": "application/json",
                "Authorization-Token": token,
                "Origin": "https://www.dishtv.in",
                "Referer": "https://www.dishtv.in/channel-guide.html"
            }
            res_epg = requests.post(channels_url, headers=epg_headers, json={}, timeout=10)
            epg_data = res_epg.json()
            
            tv = ET.Element("tv")
            channels_list = epg_data.get("programDetailsByChannel", [])

            for ch in channels_list:
                ch_id = str(ch.get("channelid", ""))
                ch_name = ch.get("channelname", "Unknown")

                if not ch_id:
                    continue

                channel_elem = ET.SubElement(tv, "channel", id=ch_id)
                display_name = ET.SubElement(channel_elem, "display-name")
                display_name.text = ch_name

                programs = ch.get("programs", [])
                for prog in programs:
                    start_time = prog.get("programstart", "")
                    stop_time = prog.get("programstop", "")
                    
                    try:
                        start_formatted = datetime.strptime(start_time.split(".")[0], "%Y-%m-%dT%H:%M:%S").strftime("%Y%m%d%H%M%S +0000")
                        stop_formatted = datetime.strptime(stop_time.split(".")[0], "%Y-%m-%dT%H:%M:%S").strftime("%Y%m%d%H%M%S +0000")
                    except:
                        start_formatted = start_time
                        stop_formatted = stop_time

                    title_text = prog.get("regional", {}).get("english", {}).get("title", "No Title")
                    desc_text = prog.get("regional", {}).get("english", {}).get("desc", "")

                    prog_elem = ET.SubElement(tv, "programme", start=start_formatted, stop=stop_formatted, channel=ch_id)
                    title_elem = ET.SubElement(prog_elem, "title", lang="en")
                    title_elem.text = title_text

                    if desc_text:
                        desc_elem = ET.SubElement(prog_elem, "desc", lang="en")
                        desc_elem.text = desc_text

            xml_bytes = ET.tostring(tv, encoding="utf-8", xml_declaration=True)
            cached_epg = xml_bytes.decode("utf-8")

    except Exception as e:
        print(f"Background update error: {e}")
    finally:
        is_updating = False

def periodic_updater():
    while True:
        update_background_tasks()
        time.sleep(180) # Har 3 minute baad playlist te tokens refresh honge

# Server start hunde hi pehli vaar background task run karo
update_background_tasks()
threading.Thread(target=periodic_updater, daemon=True).start()

@app.route('/')
def home():
    return "JioTV Zero-Latency M3U & EPG Server is Running!"

@app.route('/playlist.m3u')
def generate_m3u():
    return Response(cached_m3u, mimetype='audio/x-mpegurl')

@app.route('/epg.xml')
def generate_epg():
    return Response(cached_epg, mimetype='application/xml')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
