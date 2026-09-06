from flask import Flask, Response
import requests
import re
import threading
import time

app = Flask(__name__)

cached_m3u = '#EXTM3U\n'
cached_epg = '<?xml version="1.0" encoding="UTF-8"?>\n<tv>\n</tv>'
is_updating = False


# ==========================================
# COMMON NAME FILTER & CLEANING
# ==========================================

regional_langs = [
    'tamil',
    'telugu',
    'malayalam',
    'marathi',
    'bangla',
    'kannada',
    'gujarati',
    'odia'
]


def clean_and_filter_name(name):
    if not name:
        return None

    name = name.strip()
    low = name.lower()

    # Regional language channels filter
    if any(
        re.search(rf'\b{re.escape(x)}\b', low)
        for x in regional_langs
    ):
        return None

    # Remove Hindi
    name = re.sub(
        r'\s+Hindi\b',
        '',
        name,
        flags=re.IGNORECASE
    )

    # Remove SD
    name = re.sub(
        r'\bSD\b',
        '',
        name,
        flags=re.IGNORECASE
    )

    return re.sub(r'\s+', ' ', name).strip()


def normalize_name(name):
    cleaned = clean_and_filter_name(name)

    if not cleaned:
        return None

    name = cleaned.lower()
    name = re.sub(r'[^a-z0-9]+', '', name)

    return name.strip()


# ==========================================
# SECONDARY Zio.m3u STREAM EXTRACTOR
# SAME FILTER AS PRIMARY
# ==========================================

def get_secondary_streams():

    streams = {}

    try:

        url = (
            "https://raw.githubusercontent.com/"
            "Sflex0719/STBPLUS/refs/heads/main/Zio.m3u"
        )

        r = requests.get(url, timeout=5)

        if r.status_code != 200:
            print(
                "Failed to fetch Zio.m3u, status:",
                r.status_code
            )
            return streams

        lines = r.text.splitlines()

        raw_name = ""

        for line in lines:

            line = line.strip()

            if line.startswith("#EXTINF:"):

                if "," in line:
                    raw_name = line.split(",", 1)[1].strip()
                else:
                    raw_name = ""

            elif line and not line.startswith("#"):

                if raw_name:

                    # SAME FILTER AS PRIMARY
                    clean_raw = clean_and_filter_name(raw_name)

                    if clean_raw:

                        key = normalize_name(raw_name)

                        if key:
                            streams[key] = line

                        # Clean name matching
                        streams[clean_raw.lower()] = line

                    raw_name = ""

        print(
            f"Successfully loaded "
            f"{len(streams)} filtered secondary streams"
        )

    except Exception as e:

        print(
            "Secondary error:",
            e
        )

    return streams


# ==========================================
# DISHTV LCN FETCHER
# ==========================================

def get_dishtv_lcn_map():

    lcn_map = {}

    try:

        url = (
            "https://raw.githubusercontent.com/"
            "Diljan707/Automated-/main/"
            "dishtv_lcn_list.txt"
        )

        r = requests.get(
            url,
            timeout=5
        )

        print(
            f"DishTV LCN fetch status: {r.status_code}"
        )

        if r.status_code == 200:

            lines = r.text.splitlines()

            for line in lines:

                line = line.strip()

                if not line:
                    continue

                parts = re.split(
                    r'\||,|\t',
                    line
                )

                if len(parts) < 2:
                    continue

                p1 = parts[0].strip()
                p2 = parts[1].strip()

                if p2.isdigit():

                    ch_name = p1
                    lcn_num = p2

                elif p1.isdigit():

                    ch_name = p2
                    lcn_num = p1

                else:
                    continue

                norm_k = normalize_name(ch_name)

                if norm_k:
                    lcn_map[norm_k] = lcn_num

                lcn_map[ch_name.lower()] = lcn_num

            print(
                f"Successfully loaded "
                f"{len(lcn_map)} LCN mappings"
            )

    except Exception as e:

        print(
            "DishTV LCN fetch error:",
            e
        )

    return lcn_map


# ==========================================
# ADD ONE M3U CHANNEL ENTRY
# ==========================================

def add_m3u_entry(
    m3u,
    ch_id,
    ch_no,
    channel_name,
    logo,
    group,
    group_logo,
    stream_url,
    key_id,
    key_val,
    base_proxy_url,
    ch_token
):

    # --------------------------------------
    # Channel information
    # --------------------------------------

    m3u += (
        f'#EXTINF:-1 '
        f'tvg-id="{ch_id}" '
        f'ch-number="{ch_no}" '
        f'group-title="{group}" '
        f'group-logo="{group_logo}" '
        f'tvg-logo="{logo}",'
        f'{channel_name}\n'
    )

    # --------------------------------------
    # DRM / ClearKey
    # --------------------------------------

    has_clearkey = (
        key_id
        and key_val
        and key_id != "null"
        and key_val != "null"
    )

    if has_clearkey:

        m3u += (
            '#KODIPROP:'
            'inputstream.adaptive.license_type=clearkey\n'
        )

        m3u += (
            f'#KODIPROP:'
            f'inputstream.adaptive.license_key='
            f'{key_id}:{key_val}\n'
        )

    else:

        proxy = f'{base_proxy_url}{ch_id}/'

        m3u += (
            '#KODIPROP:'
            'inputstream.adaptive.license_type=clearkey\n'
        )

        m3u += (
            f'#KODIPROP:'
            f'inputstream.adaptive.license_key='
            f'{proxy}\n'
        )

    # --------------------------------------
    # User Agent
    # --------------------------------------

    m3u += (
        '#EXTVLCOPT:http-user-agent='
        'plaYtv/7.1.5\n'
    )

    # --------------------------------------
    # Headers
    # --------------------------------------

    if ch_token:

        m3u += (
            f'#EXTHTTP:{{'
            f'"cookie":"{ch_token}",'
            f'"Origin":"https://www.jiotv.com/",'
            f'"Referer":"https://www.jiotv.com/"'
            f'}}\n'
        )

    else:

        m3u += (
            '#EXTHTTP:{'
            '"Origin":"https://www.jiotv.com/",'
            '"Referer":"https://www.jiotv.com/"'
            '}\n'
        )

    # --------------------------------------
    # ORIGINAL STREAM URL
    # --------------------------------------

    final_url = stream_url

    if ch_token:

        separator = (
            "&"
            if "?" in final_url
            else "?"
        )

        final_url = (
            f'{final_url}'
            f'{separator}'
            f'{ch_token}'
        )

    m3u += f'{final_url}\n\n'

    return m3u


# ==========================================
# BACKGROUND UPDATE
# ==========================================

def update_m3u_background():

    global cached_m3u
    global cached_epg
    global is_updating

    if is_updating:
        return

    is_updating = True

    try:

        # ==================================
        # 1. STAR SPORTS TOKENS
        # ==================================

        star_tokens = {}

        try:

            url = (
                "https://allinonereborn2.online/"
                "jtv-fetch/jstarcookie/cookie.json"
            )

            r = requests.get(
                url,
                timeout=6
            )

            if r.status_code == 200:

                data = r.json()

                for item in data.get(
                    "failed_results",
                    []
                ):

                    ch_id = str(
                        item.get(
                            "channel_id",
                            ""
                        )
                    )

                    final_url = (
                        item.get(
                            "error_details",
                            {}
                        ).get(
                            "final_url",
                            ""
                        )
                    )

                    m = re.search(
                        r'__hdnea__=([^&]+)',
                        final_url
                    )

                    if m:

                        star_tokens[ch_id] = (
                            f'__hdnea__={m.group(1)}'
                        )

        except Exception:
            pass


        # ==================================
        # 2. GLOBAL TOKEN
        # ==================================

        global_token = ""

        token_urls = [

            "https://allinonereborn2.online/"
            "jstrweb2/cookies.json",

            "https://allinonereborn2.online/"
            "jstrweb3/cookies.json",

            "https://allinonereborn2.online/"
            "jstrweb4/cookies.json"
        ]

        for url in token_urls:

            try:

                r = requests.get(
                    url,
                    timeout=3
                )

                if r.status_code == 200:

                    for item in r.json():

                        if (
                            isinstance(item, dict)
                            and item.get("cookie")
                        ):

                            global_token = (
                                item["cookie"]
                            )

                            break

                    if global_token:
                        break

            except Exception:
                continue


        # ==================================
        # 3. SECONDARY STREAMS
        # ==================================

        secondary_streams = (
            get_secondary_streams()
        )


        # ==================================
        # 4. DISHTV LCN
        # ==================================

        dishtv_lcn_map = (
            get_dishtv_lcn_map()
        )


        # ==================================
        # 5. BASE PROXY URL
        # ==================================

        base_proxy_url = (
            "https://streamflexsmm.in/license/"
        )

        try:

            url = (
                "https://raw.githubusercontent.com/"
                "Sflex0719/STBPLUS/main/"
                "ZioMobile.m3u"
            )

            r = requests.get(
                url,
                timeout=3
            )

            if r.status_code == 200:

                for line in r.text.splitlines():

                    if "license_key=" not in line:
                        continue

                    key = (
                        line.split(
                            "license_key=",
                            1
                        )[1].strip()
                    )

                    if (
                        not key
                        or key == "null:null"
                    ):
                        continue

                    m = re.search(
                        r'(https?://[^\s]+?/)(?:\d+/)?$',
                        key
                    )

                    if m:

                        base_proxy_url = (
                            m.group(1)
                        )

                    else:

                        base_proxy_url = re.sub(
                            r'\d+/?$',
                            '',
                            key
                        )

                    break

        except Exception:
            pass


        # ==================================
        # 6. PRIMARY CHANNELS
        # ==================================

        url = (
            "https://jjtvxweb.pages.dev/"
            "jstr4web.json"
        )

        r = requests.get(
            url,
            timeout=6
        )

        channels = r.json()


        # ==================================
        # M3U + EPG
        # ==================================

        m3u = (
            '#EXTM3U '
            'url-tvg="http://localhost:10000/epg.xml"\n'
        )

        epg = (
            '<?xml version="1.0" '
            'encoding="UTF-8"?>\n'
            '<!DOCTYPE tv SYSTEM "xmltv.dtd">\n'
            '<tv>\n'
        )


        fallback_counter = 1

        primary_count = 0
        secondary_count = 0
        matched_lcn_count = 0


        # ==================================
        # PROCESS CHANNELS
        # ==================================

        for ch in channels:

            raw_name = ch.get(
                "name",
                "Unknown"
            )

            ch_id = str(
                ch.get(
                    "id",
                    ""
                )
            )

            # --------------------------------
            # PRIMARY FILTER
            # --------------------------------

            clean_name = (
                clean_and_filter_name(
                    raw_name
                )
            )

            if not clean_name:
                continue

            match_name = (
                normalize_name(
                    raw_name
                )
            )

            lower_name = (
                clean_name.lower()
            )

            if not match_name:
                continue


            # --------------------------------
            # PRIMARY DATA
            # --------------------------------

            primary_url = ch.get(
                "url",
                ""
            )

            logo = ch.get(
                "logo",
                ""
            )

            category = ch.get(
                "category",
                "Unknown"
            )

            if not primary_url:
                continue


            group = (
                f"JioTV+ ▶ | {category}"
            )

            group_logo = (
                "https://i.postimg.cc/"
                "52qG6sKt/STREAMXi.png"
            )


            # =================================
            # FIND SECONDARY
            # =================================

            sec_stream_url = (
                secondary_streams.get(
                    match_name
                )
                or
                secondary_streams.get(
                    lower_name
                )
            )


            # Fuzzy matching
            if not sec_stream_url:

                for k, v in secondary_streams.items():

                    if (
                        match_name in k
                        or k in match_name
                        or lower_name in k
                        or k in lower_name
                    ):

                        sec_stream_url = v
                        break


            # =================================
            # LCN MATCH
            # =================================

            ch_no = (
                dishtv_lcn_map.get(
                    match_name
                )
                or
                dishtv_lcn_map.get(
                    lower_name
                )
            )


            if not ch_no:

                for k, v in dishtv_lcn_map.items():

                    if (
                        match_name in k
                        or k in match_name
                        or lower_name in k
                        or k in lower_name
                    ):

                        ch_no = v
                        break


            if ch_no:

                matched_lcn_count += 1

            else:

                ch_no = str(
                    fallback_counter
                )

                fallback_counter += 1


            # =================================
            # DRM DATA
            # =================================

            key_id = ch.get(
                "keyId",
                ""
            )

            key_val = ch.get(
                "key",
                ""
            )


            # =================================
            # TOKEN
            # =================================

            ch_token = (
                star_tokens.get(ch_id)
                or global_token
            )


            # =================================
            # PRIMARY ENTRY
            # =================================

            m3u = add_m3u_entry(

                m3u,

                ch_id,

                ch_no,

                clean_name,

                logo,

                group,

                group_logo,

                primary_url,

                key_id,

                key_val,

                base_proxy_url,

                ch_token
            )

            primary_count += 1


            # =================================
            # SECONDARY ENTRY
            # =================================

            if sec_stream_url:

                # Same filtered/cleaned name
                # Same LCN
                # Separate ORIGINAL secondary URL

                m3u = add_m3u_entry(

                    m3u,

                    ch_id,

                    ch_no,

                    clean_name,

                    logo,

                    group,

                    group_logo,

                    sec_stream_url,

                    key_id,

                    key_val,

                    base_proxy_url,

                    ch_token
                )

                secondary_count += 1


            # =================================
            # EPG
            # =================================

            epg += (
                f'  <channel id="{ch_id}">\n'
            )

            epg += (
                f'    <display-name '
                f'lang="en">'
                f'{clean_name}'
                f'</display-name>\n'
            )

            if logo:

                epg += (
                    f'    <icon '
                    f'src="{logo}" />\n'
                )

            epg += (
                '  </channel>\n'
            )


        # ==================================
        # FINISH EPG
        # ==================================

        epg += '</tv>'


        # ==================================
        # SAVE CACHE
        # ==================================

        cached_m3u = m3u
        cached_epg = epg


        print(
            "======================================"
        )

        print(
            "Update finished!"
        )

        print(
            f"Primary channels: {primary_count}"
        )

        print(
            f"Secondary channels: {secondary_count}"
        )

        print(
            f"GitHub LCN matched: "
            f"{matched_lcn_count}"
        )

        print(
            "======================================"
        )


    except Exception as e:

        print(
            "Background update error:",
            e
        )

    finally:

        is_updating = False


# ==========================================
# PERIODIC UPDATER
# ==========================================

def periodic_updater():

    while True:

        update_m3u_background()

        time.sleep(180)


# ==========================================
# INITIAL UPDATE
# ==========================================

update_m3u_background()


threading.Thread(
    target=periodic_updater,
    daemon=True
).start()


# ==========================================
# HOME
# ==========================================

@app.route('/')
def home():

    return (
        "JioTV M3U Server with "
        "Primary + Secondary Streams "
        "is Running!"
    )


# ==========================================
# PLAYLIST
# ==========================================

@app.route('/playlist.m3u')
def generate_m3u():

    return Response(
        cached_m3u,
        mimetype='audio/x-mpegurl'
    )


# ==========================================
# EPG
# ==========================================

@app.route('/epg.xml')
def generate_epg():

    return Response(
        cached_epg,
        mimetype='application/xml'
    )


# ==========================================
# START SERVER
# ==========================================

if __name__ == '__main__':

    app.run(
        host='0.0.0.0',
        port=10000
    )
