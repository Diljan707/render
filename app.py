from flask import Flask, Response
import requests
import re
import threading
import time

app = Flask(__name__)

cached_m3u = '#EXTM3U\n'
cached_epg = '<?xml version="1.0" encoding="UTF-8"?>\n<tv>\n</tv>'
is_updating = False


# ==============================
# COMMON NAME FILTER
# ==============================

regional_langs = [
    'tamil',
    'telugu',
    'malayalam',
    'marathi',
    'bengali',
    'kannada',
    'gujarati',
    'odia'
]


def clean_and_filter_name(raw_name):
    if not raw_name:
        return None

    name = raw_name.strip()
    name_lower = name.lower()

    # Regional channels skip
    for lang in regional_langs:
        if re.search(rf'\b{re.escape(lang)}\b', name_lower):
            return None

    # Hindi remove
    name = re.sub(r'\s+Hindi\b', '', name, flags=re.IGNORECASE)

    # Extra spaces clean
    name = re.sub(r'\s+', ' ', name).strip()

    return name


# ==============================
# NORMALIZED MATCH NAME
# ==============================

def normalize_name(name):
    """
    Primary te secondary channel names nu
    same format ch leke aunda hai.
    """

    cleaned = clean_and_filter_name(name)

    if not cleaned:
        return None

    # lowercase
    cleaned = cleaned.lower()

    # punctuation remove
    cleaned = re.sub(r'[^a-z0-9]+', ' ', cleaned)

    # extra spaces
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    return cleaned


# ==============================
# BACKGROUND UPDATE
# ==============================

def update_m3u_background():

    global cached_m3u, cached_epg, is_updating

    if is_updating:
        return

    is_updating = True

    try:

        # ==========================================
        # 1. STAR SPORTS DYNAMIC TOKENS
        # ==========================================

        COOKIE_STAR_SPORTS = (
            "https://allinonereborn2.online/"
            "jtv-fetch/jstarcookie/cookie.json"
        )

        star_tokens = {}

        try:

            res = requests.get(
                COOKIE_STAR_SPORTS,
                timeout=6
            )

            if res.status_code == 200:

                data = res.json()

                if data and "failed_results" in data:

                    for item in data["failed_results"]:

                        ch_id_str = str(
                            item.get("channel_id")
                        )

                        err_details = item.get(
                            "error_details",
                            {}
                        )

                        final_url = err_details.get(
                            "final_url",
                            ""
                        )

                        if "__hdnea__=" in final_url:

                            match = re.search(
                                r'__hdnea__=([^&]+)',
                                final_url
                            )

                            if match:

                                star_tokens[ch_id_str] = (
                                    f"__hdnea__={match.group(1)}"
                                )

        except Exception:
            pass


        # ==========================================
        # 2. GLOBAL FALLBACK TOKEN
        # ==========================================

        token_urls = [

            "https://allinonereborn2.online/"
            "jstrweb2/cookies.json",

            "https://allinonereborn2.online/"
            "jstrweb3/cookies.json",

            "https://allinonereborn2.online/"
            "jstrweb4/cookies.json"
        ]

        global_token = ""

        for url in token_urls:

            try:

                res = requests.get(
                    url,
                    timeout=3
                )

                if res.status_code == 200:

                    for item in res.json():

                        if (
                            isinstance(item, dict)
                            and "cookie" in item
                        ):

                            global_token = item["cookie"]
                            break

                    if global_token:
                        break

            except Exception:
                continue


        # ==========================================
        # 3. SECONDARY Zio.m3u
        # ==========================================

        secondary_streams = {}

        try:

            sec_url = (
                "https://raw.githubusercontent.com/"
                "Sflex0719/STBPLUS/refs/heads/main/"
                "Zio.m3u"
            )

            sec_res = requests.get(
                sec_url,
                timeout=5
            )

            if sec_res.status_code == 200:

                lines = sec_res.text.splitlines()

                current_raw_name = ""

                for line in lines:

                    line = line.strip()

                    if line.startswith("#EXTINF:"):

                        if "," in line:

                            current_raw_name = (
                                line.split(",", 1)[1].strip()
                            )

                    elif (
                        line
                        and not line.startswith("#")
                    ):

                        if current_raw_name:

                            # SAME FILTER AS PRIMARY
                            match_name = normalize_name(
                                current_raw_name
                            )

                            if match_name:

                                secondary_streams[
                                    match_name
                                ] = line

                            current_raw_name = ""

        except Exception:
            pass


        # ==========================================
        # 4. DISHTV LCN
        # ==========================================

        dishtv_lcn_map = {}

        try:

            dishtv_url = (
                "https://raw.githubusercontent.com/"
                "your-username/repo/main/"
                "dishtv_channels.json"
            )

            d_res = requests.get(
                dishtv_url,
                timeout=4
            )

            if d_res.status_code == 200:

                d_data = d_res.json()

                if isinstance(d_data, dict):

                    dishtv_lcn_map = {
                        str(k).lower(): str(v)
                        for k, v in d_data.items()
                    }

        except Exception:
            pass


        # ==========================================
        # 5. BASE PROXY URL
        # ==========================================

        base_proxy_url = (
            "https://streamflexsmm.in/license/"
        )

        try:

            target_m3u_url = (
                "https://raw.githubusercontent.com/"
                "Sflex0719/STBPLUS/main/"
                "ZioMobile.m3u"
            )

            res = requests.get(
                target_m3u_url,
                timeout=3
            )

            if res.status_code == 200:

                for line in res.text.splitlines():

                    if "license_key=" in line:

                        l_key = (
                            line.split(
                                "license_key=",
                                1
                            )[1].strip()
                        )

                        if (
                            l_key
                            and l_key != "null:null"
                        ):

                            match = re.search(
                                r'(https?://[^\s]+?/)(?:\d+/)?$',
                                l_key
                            )

                            if match:

                                base_proxy_url = (
                                    match.group(1)
                                )

                            else:

                                base_proxy_url = re.sub(
                                    r'\d+/?$',
                                    '',
                                    l_key
                                )

                            break

        except Exception:
            pass


        # ==========================================
        # 6. PRIMARY CHANNELS
        # ==========================================

        channels_res = requests.get(
            "https://jjtvxweb.pages.dev/jstr4web.json",
            timeout=6
        )

        channels = channels_res.json()

        m3u = (
            '#EXTM3U '
            'url-tvg="http://localhost:10000/epg.xml"\n'
        )

        epg_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE tv SYSTEM "xmltv.dtd">\n'
            '<tv>\n'
        )

        fallback_counter = 1


        # ==========================================
        # CHANNEL LOOP
        # ==========================================

        for ch in channels:

            raw_name = ch.get(
                'name',
                'Unknown'
            )

            ch_id = str(
                ch.get('id', '')
            )


            # ======================================
            # SAME FILTER FOR PRIMARY
            # ======================================

            clean_name = clean_and_filter_name(
                raw_name
            )

            if not clean_name:
                continue


            match_name = normalize_name(
                raw_name
            )

            if not match_name:
                continue


            url = ch.get(
                'url',
                ''
            )

            logo = ch.get(
                'logo',
                ''
            )

            category = ch.get(
                'category',
                'Unknown'
            )

            group = (
                f"JioTV+ ▶ | {category}"
            )

            group_logo = (
                "https://i.postimg.cc/"
                "52qG6sKt/STREAMXi.png"
            )


            if not url:
                continue


            # ======================================
            # LCN
            # ======================================

            name_lower = raw_name.lower()

            ch_no = (
                dishtv_lcn_map.get(name_lower)
                or dishtv_lcn_map.get(ch_id)
            )

            if not ch_no:

                ch_no = str(
                    fallback_counter
                )

                fallback_counter += 1


            formatted_name = (
                f"{ch_no} - {clean_name}"
            )


            # ======================================
            # CLEARKEY
            # ======================================

            key_id = ch.get(
                'keyId',
                ''
            )

            key_val = ch.get(
                'key',
                ''
            )

            has_clearkey = (
                key_id
                and key_val
                and key_id != "null"
                and key_val != "null"
            )


            # ======================================
            # TOKEN
            # ======================================

            ch_token = (
                star_tokens.get(ch_id)
                or global_token
            )


            if ch_token:

                if '?' not in url:

                    final_url = (
                        f"{url}?{ch_token}"
                    )

                else:

                    final_url = (
                        f"{url}&{ch_token}"
                    )

            else:

                final_url = url


            # ======================================
            # PRIMARY M3U
            # ======================================

            m3u += (
                f'#EXTINF:-1 '
                f'tvg-id="{ch_id}" '
                f'ch-number="{ch_no}" '
                f'group-title="{group}" '
                f'group-logo="{group_logo}" '
                f'tvg-logo="{logo}",'
                f'{formatted_name}\n'
            )


            if has_clearkey:

                license_key = (
                    f"{key_id}:{key_val}"
                )

                m3u += (
                    '#KODIPROP:'
                    'inputstream.adaptive.license_type='
                    'clearkey\n'
                )

                m3u += (
                    '#KODIPROP:'
                    'inputstream.adaptive.license_key='
                    f'{license_key}\n'
                )

            else:

                custom_license_proxy = (
                    f"{base_proxy_url}"
                    f"{ch_id}/"
                )

                m3u += (
                    '#KODIPROP:'
                    'inputstream.adaptive.license_type='
                    'clearkey\n'
                )

                m3u += (
                    '#KODIPROP:'
                    'inputstream.adaptive.license_key='
                    f'{custom_license_proxy}\n'
                )


            m3u += (
                '#EXTVLCOPT:http-user-agent='
                'plaYtv/7.1.5\n'
            )


            if ch_token:

                m3u += (
                    '#EXTHTTP:'
                    f'{{"cookie":"{ch_token}",'
                    '"Origin":"https://www.jiotv.com/",'
                    '"Referer":"https://www.jiotv.com/"}}\n'
                )

            else:

                m3u += (
                    '#EXTHTTP:'
                    '{"Origin":"https://www.jiotv.com/",'
                    '"Referer":"https://www.jiotv.com/"}\n'
                )


            m3u += (
                f'{final_url}\n'
            )


            # ======================================
            # SECONDARY MATCH
            # ======================================

            sec_stream_url = (
                secondary_streams.get(
                    match_name
                )
            )


            if sec_stream_url:

                m3u += (
                    f'#EXTINF:-1 '
                    f'tvg-id="{ch_id}" '
                    f'ch-number="{ch_no}" '
                    f'group-title="{group}" '
                    f'group-logo="{group_logo}" '
                    f'tvg-logo="{logo}",'
                    f'{formatted_name} [Backup]\n'
                )

                m3u += (
                    f'{sec_stream_url}\n'
                )


            m3u += '\n'


            # ======================================
            # EPG
            # ======================================

            epg_xml += (
                f'  <channel id="{ch_id}">\n'
            )

            epg_xml += (
                f'    <display-name lang="en">'
                f'{clean_name}'
                f'</display-name>\n'
            )

            if logo:

                epg_xml += (
                    f'    <icon src="{logo}" />\n'
                )

            epg_xml += (
                '  </channel>\n'
            )


        epg_xml += '</tv>'


        # ==========================================
        # CACHE UPDATE
        # ==========================================

        cached_m3u = m3u
        cached_epg = epg_xml


        print(
            "Playlist updated successfully."
        )


    except Exception as e:

        print(
            f"Background update error: {e}"
        )


    finally:

        is_updating = False


# ==============================================
# PERIODIC UPDATE - EVERY 3 MINUTES
# ==============================================

def periodic_updater():

    while True:

        update_m3u_background()

        time.sleep(180)


# Initial update
update_m3u_background()


threading.Thread(
    target=periodic_updater,
    daemon=True
).start()


# ==============================================
# FLASK ROUTES
# ==============================================

@app.route('/')
def home():

    return (
        "JioTV M3U Server with "
        "Unified Filtering & Fallback is Running!"
    )


@app.route('/playlist.m3u')
def generate_m3u():

    return Response(
        cached_m3u,
        mimetype='audio/x-mpegurl'
    )


@app.route('/epg.xml')
def generate_epg():

    return Response(
        cached_epg,
        mimetype='application/xml'
    )


# ==============================================
# START SERVER
# ==============================================

if __name__ == '__main__':

    app.run(
        host='0.0.0.0',
        port=10000
    )
