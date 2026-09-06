from flask import Flask, Response
import requests
import re
import threading
import time

app = Flask(__name__)

cached_m3u = '#EXTM3U\n'
cached_epg = '<?xml version="1.0" encoding="UTF-8"?>\n<tv>\n</tv>'
is_updating = False

def update_m3u_background():
    global cached_m3u, cached_epg, is_updating
    if is_updating:
        return
    is_updating = True
    
    try:
        # 1. Star Sports dynamic cookies fetch karo
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

        # 2. Global fallback cookies fetch karo
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

        # Common Regional filter and cleaning function
        regional_langs = ['tamil', 'telugu', 'malayalam', 'marathi', 'bengali', 'kannada', 'gujarati', 'odia']

        def clean_and_filter_name(raw_name):
            name_lower = raw_name.lower()
            # Regional check
            for lang in regional_langs:
                if lang in name_lower:
                    return None  # Skip this channel
            
            # Remove " Hindi"
            cleaned = raw_name
            if " hindi" in name_lower:
                cleaned = re.sub(r'\s+Hindi\b', '', raw_name, flags=re.IGNORECASE)
            
            return cleaned.strip()

        # 3. Secondary Zio.m3u fetch karo te ohi filter lagao
        secondary_streams = {}
        try:
            sec_url = "https://raw.githubusercontent.com/Sflex0719/STBPLUS/refs/heads/main/Zio.m3u"
            sec_res = requests.get(sec_url, timeout=5)
            if sec_res.status_code == 200:
                lines = sec_res.text.splitlines()
                current_raw_name = ""
                for line in lines:
                    line = line.strip()
                    if line.startswith("#EXTINF:"):
                        if "," in line:
                            current_raw_name = line.split(",")[-1].strip()
                    elif line and not line.startswith("#"):
                        if current_raw_name:
                            processed_name = clean_and_filter_name(current_raw_name)
                            if processed_name:
                                secondary_streams[processed_name.lower()] = line
                            current_raw_name = ""
        except Exception:
            pass

        # 4. DishTV LCN Source Fetch Karo
        dishtv_lcn_map = {}
        try:
            dishtv_url = "https://raw.githubusercontent.com/your-username/repo/main/dishtv_channels.json"
            d_res = requests.get(dishtv_url, timeout=4)
            if d_res.status_code == 200:
                d_data = d_res.json()
                if isinstance(d_data, dict):
                    dishtv_lcn_map = {str(k).lower(): str(v) for k, v in d_data.items()}
        except Exception:
            pass

        # 5. Base Proxy URL
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

        # 6. Channels JSON fetch te M3U generation
        channels_res = requests.get("https://jjtvxweb.pages.dev/jstr4web.json", timeout=6)
        channels = channels_res.json()
        
        m3u = '#EXTM3U url-tvg="http://localhost:10000/epg.xml"\n'
        epg_xml = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE tv SYSTEM "xmltv.dtd">\n<tv>\n'
        
        fallback_counter = 1
        
        for ch in channels:
            raw_name = ch.get('name', 'Unknown')
            ch_id = str(ch.get('id', ''))
            
            # Apply same filter & cleaning function
            clean_name = clean_and_filter_name(raw_name)
            if not clean_name:
                continue
                
            url = ch.get('url', '')
            logo = ch.get('logo', '')
            category = ch.get('category', 'Unknown')
            group = f"JioTV+ ▶ | {category}"
            group_logo = "https://i.postimg.cc/52qG6sKt/STREAMXi.png"
            
            if not url:
                continue
                
            name_lower = raw_name.lower()
            ch_no = dishtv_lcn_map.get(name_lower) or dishtv_lcn_map.get(ch_id)
            if not ch_no:
                ch_no = str(fallback_counter)
                fallback_counter += 1
                
            formatted_name = f"{ch_no} - {clean_name}"
                
            key_id = ch.get('keyId', '')
            key_val = ch.get('key', '')
            has_clearkey = key_id and key_val and key_id != "null" and key_val != "null"
            
            ch_token = star_tokens.get(ch_id) or global_token
            final_url = f"{url}?{ch_token}" if ch_token and '?' not in url else f"{url}&{ch_token}" if ch_token else url
            
            # Primary Stream Entry
            m3u += f'#EXTINF:-1 tvg-id="{ch_id}" ch-number="{ch_no}" group-title="{group}" group-logo="{group_logo}" tvg-logo="{logo}",{formatted_name}\n'
            
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
                
            m3u += f'{final_url}\n'

            # Secondary Backup Stream Entry (Exact same group, name, ID, and LCN for seamless folding)
            sec_stream_url = secondary_streams.get(clean_name.lower())
            if sec_stream_url:
                m3u += f'#EXTINF:-1 tvg-id="{ch_id}" ch-number="{ch_no}" group-title="{group}" group-logo="{group_logo}" tvg-logo="{logo}",{formatted_name}\n'
                m3u += f'#KODIPROP:inputstream.adaptive.license_type=clearkey\n'
                m3u += f'#KODIPROP:inputstream.adaptive.license_key={base_proxy_url}{ch_id}/\n'
                m3u += f'#EXTVLCOPT:http-user-agent=plaYtv/7.1.5\n'
                m3u += f'{sec_stream_url}\n'

            m3u += '\n'

            # EPG channel tag
            epg_xml += f'  <channel id="{ch_id}">\n'
            epg_xml += f'    <display-name lang="en">{clean_name}</display-name>\n'
            if logo:
                epg_xml += f'    <icon src="{logo}" />\n'
            epg_xml += f'  </channel>\n'

        epg_xml += '</tv>'

        cached_m3u = m3u
        cached_epg = epg_xml
    except Exception as e:
        print(f"Background update error: {e}")
    finally:
        is_updating = False

def periodic_updater():
    while True:
        update_m3u_background()
        time.sleep(180)

update_m3u_background()
threading.Thread(target=periodic_updater, daemon=True).start()

@app.route('/')
def home():
    return "JioTV M3U Server with Auto-Folding Support is Running!"

@app.route('/playlist.m3u')
def generate_m3u():
    return Response(cached_m3u, mimetype='audio/x-mpegurl')

@app.route('/epg.xml')
def generate_epg():
    return Response(cached_epg, mimetype='application/xml')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
            
