from flask import Flask, Response
import requests
import re
import threading
import time

app = Flask(__name__)

cached_m3u = "#EXTM3U\n"
cached_epg = '<?xml version="1.0" encoding="UTF-8"?>\n<tv>\n</tv>'
is_updating = False


# =========================================================
# CUSTOM DISHTV LCN LIST
# =========================================================
# Tuhada poora LCN_TEXT list ethe EXACTLY same rahega.
# Jo tusi upar bheji hai, oh poori list paste karo.

LCN_TEXT = """
100: Star Plus HD
101: Star Plus
102: Zee TV HD
103: Zee tv
104: SONY ENTERTAINMENT TELEVISION HD
105: SONY ENTERTAINMENT TELEVISION
106: SONY SAB HD
107: SONY SAB
108: &TV HD
109: Dangal TV

# ---------------------------------------------------------
# IMPORTANT:
# ETHE TUSI APNI POORI LCN LIST PASTE KARNI AA.
# 100 ton 4066 tak jo list tusi bheji hai.
# ---------------------------------------------------------

4064: R. Bangla
4065: Living India News
4066: Bharat Express
"""


# =========================================================
# NORMALIZE NAME
# =========================================================

def normalize_name(name):
    name = str(name or "").lower().strip()
    name = re.sub(r"\s+", " ", name)
    return name


# =========================================================
# BUILD DISHTV LCN MAP
# =========================================================

dishtv_lcn_map = {}

for line in LCN_TEXT.splitlines():

    line = line.strip()

    if not line or ":" not in line:
        continue

    lcn, name = line.split(":", 1)

    lcn = lcn.strip()
    name = normalize_name(name)

    if lcn and name:

        # Duplicate channel name hove taan
        # LAST LCN use hovega.
        dishtv_lcn_map[name] = lcn


# =========================================================
# BACKGROUND UPDATE
# =========================================================

def update_m3u_background():

    global cached_m3u
    global cached_epg
    global is_updating

    if is_updating:
        return

    is_updating = True

    try:

        # =================================================
        # 1. STAR SPORTS TOKEN
        # =================================================

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

                if isinstance(data, dict):

                    failed_results = data.get(
                        "failed_results",
                        []
                    )

                    for item in failed_results:

                        if not isinstance(item, dict):
                            continue

                        ch_id_str = str(
                            item.get(
                                "channel_id",
                                ""
                            )
                        )

                        err_details = item.get(
                            "error_details",
                            {}
                        )

                        if not isinstance(
                            err_details,
                            dict
                        ):
                            continue

                        final_url = str(
                            err_details.get(
                                "final_url",
                                ""
                            )
                        )

                        if "__hdnea__=" in final_url:

                            match = re.search(
                                r"__hdnea__=([^&]+)",
                                final_url
                            )

                            if match:

                                star_tokens[
                                    ch_id_str
                                ] = (
                                    "__hdnea__="
                                    + match.group(1)
                                )

        except Exception as e:

            print(
                f"Star token error: {e}"
            )


        # =================================================
        # 2. GLOBAL COOKIE
        # =================================================

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

                if res.status_code != 200:
                    continue

                data = res.json()

                if isinstance(data, list):

                    for item in data:

                        if (
                            isinstance(item, dict)
                            and item.get("cookie")
                        ):

                            global_token = str(
                                item["cookie"]
                            )

                            break

                if global_token:
                    break

            except Exception as e:

                print(
                    f"Cookie error: {e}"
                )

                continue


        # =================================================
        # 3. REGIONAL FILTER
        # =================================================

        regional_langs = [

            "tamil",
            "telugu",
            "malayalam",
            "marathi",
            "bengali",
            "kannada",
            "gujarati",
            "odia"
        ]


        def clean_and_filter_name(raw_name):

            raw_name = str(
                raw_name or ""
            ).strip()

            name_lower = raw_name.lower()

            for lang in regional_langs:

                if lang in name_lower:
                    return None

            cleaned = raw_name

            if " hindi" in name_lower:

                cleaned = re.sub(
                    r"\s+Hindi\b",
                    "",
                    raw_name,
                    flags=re.IGNORECASE
                )

            return cleaned.strip()


        # =================================================
        # 4. SECONDARY ZIO M3U
        # =================================================

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

                    # -------------------------------------
                    # CHANNEL NAME
                    # -------------------------------------

                    if line.startswith(
                        "#EXTINF:"
                    ):

                        match = re.search(
                            r",(.+)$",
                            line
                        )

                        if match:

                            current_raw_name = (
                                match.group(1).strip()
                            )

                    # -------------------------------------
                    # STREAM URL
                    # -------------------------------------

                    elif (
                        line
                        and not line.startswith("#")
                        and current_raw_name
                    ):

                        cleaned_name = (
                            clean_and_filter_name(
                                current_raw_name
                            )
                        )

                        if cleaned_name:

                            key = normalize_name(
                                cleaned_name
                            )

                            secondary_streams[
                                key
                            ] = line

                        current_raw_name = ""

        except Exception as e:

            print(
                f"Secondary M3U error: {e}"
            )


        # =================================================
        # 5. CHANNEL JSON
        # =================================================

        channel_url = (
            "https://jjtvxweb.pages.dev/"
            "jstr4web.json"
        )

        res = requests.get(
            channel_url,
            timeout=10
        )

        res.raise_for_status()

        channels = res.json()

        if not isinstance(channels, list):

            raise ValueError(
                "Channel JSON list nahi hai"
            )


        # =================================================
        # 6. BUILD M3U
        # =================================================

        m3u_lines = [
            "#EXTM3U"
        ]

        epg_channels = []

        fallback_lcn = 1


        for ch in channels:

            if not isinstance(ch, dict):
                continue


            # ---------------------------------------------
            # CHANNEL NAME
            # ---------------------------------------------

            raw_name = str(
                ch.get("name")
                or ch.get("channel_name")
                or ""
            ).strip()

            if not raw_name:
                continue


            # ---------------------------------------------
            # CHANNEL ID
            # ---------------------------------------------

            ch_id = str(
                ch.get("id")
                or ch.get("channel_id")
                or ""
            ).strip()


            # ---------------------------------------------
            # CLEAN NAME
            # ---------------------------------------------

            clean_name = (
                clean_and_filter_name(
                    raw_name
                )
            )

            if not clean_name:
                continue


            # =================================================
            # SAME DISHTV LCN MATCHING LOGIC
            # =================================================

            normalized_raw = normalize_name(
                raw_name
            )

            normalized_clean = normalize_name(
                clean_name
            )


            # First raw name match
            channel_no = (
                dishtv_lcn_map.get(
                    normalized_raw
                )
            )


            # Then cleaned name match
            if not channel_no:

                channel_no = (
                    dishtv_lcn_map.get(
                        normalized_clean
                    )
                )


            # Fallback
            if not channel_no:

                channel_no = str(
                    fallback_lcn
                )

                fallback_lcn += 1


            # ---------------------------------------------
            # FINAL DISPLAY NAME
            # ---------------------------------------------

            display_name = (
                f"{channel_no} - {clean_name}"
            )


            # ---------------------------------------------
            # PRIMARY STREAM
            # ---------------------------------------------

            primary_url = str(
                ch.get("url")
                or ch.get("stream_url")
                or ch.get("link")
                or ""
            ).strip()

            if not primary_url:
                continue


            # =================================================
            # PRIMARY ENTRY
            # =================================================

            m3u_lines.append(
                f'#EXTINF:-1 '
                f'tvg-id="{ch_id}" '
                f'tvg-name="{display_name}",'
                f'{display_name}'
            )


            # Global cookie
            if global_token:

                m3u_lines.append(
                    f"#EXTHTTP:{global_token}"
                )


            # Star token, if available
            if ch_id in star_tokens:

                m3u_lines.append(
                    f"#EXTHTTP:"
                    f"{star_tokens[ch_id]}"
                )


            m3u_lines.append(
                primary_url
            )


            # =================================================
            # SECONDARY MATCH
            # =================================================

            secondary_url = (
                secondary_streams.get(
                    normalized_clean
                )
            )


            if not secondary_url:

                secondary_url = (
                    secondary_streams.get(
                        normalized_raw
                    )
                )


            # =================================================
            # SECONDARY ENTRY
            # =================================================

            if secondary_url:

                m3u_lines.append(
                    f'#EXTINF:-1 '
                    f'tvg-id="{ch_id}" '
                    f'tvg-name="{display_name}",'
                    f'{display_name}'
                )

                m3u_lines.append(
                    secondary_url
                )


            # =================================================
            # EPG
            # =================================================

            if ch_id:

                safe_name = (
                    display_name
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )

                epg_channels.append(
                    f'  <channel id="{ch_id}">'
                    f'<display-name>'
                    f'{safe_name}'
                    f'</display-name>'
                    f'</channel>'
                )


        # =================================================
        # 7. FINAL EPG
        # =================================================

        epg_xml = (
            '<?xml version="1.0" '
            'encoding="UTF-8"?>\n'
            '<tv>\n'
            + "\n".join(epg_channels)
            + "\n</tv>"
        )


        # =================================================
        # 8. CACHE UPDATE
        # =================================================

        cached_m3u = (
            "\n".join(m3u_lines)
            + "\n"
        )

        cached_epg = epg_xml

        print(
            f"Playlist updated: "
            f"{len(m3u_lines)} lines"
        )


    # =====================================================
    # IMPORTANT: THIS EXCEPT MUST ALIGN WITH TRY
    # =====================================================

    except Exception as e:

        print(
            f"Background update error: {e}"
        )


    finally:

        is_updating = False


# =========================================================
# PERIODIC UPDATER
# =========================================================

def periodic_updater():

    while True:

        try:

            update_m3u_background()

        except Exception as e:

            print(
                f"Updater error: {e}"
            )

        time.sleep(180)


# =========================================================
# ROUTES
# =========================================================

@app.route("/")
def index():

    return "IPTV Server Running"


@app.route("/playlist.m3u")
def playlist():

    return Response(
        cached_m3u,
        mimetype="audio/x-mpegurl"
    )


@app.route("/epg.xml")
def epg():

    return Response(
        cached_epg,
        mimetype="application/xml"
    )


# =========================================================
# START SERVER
# =========================================================

if __name__ == "__main__":

    threading.Thread(
        target=periodic_updater,
        daemon=True
    ).start()

    app.run(
        host="0.0.0.0",
        port=10000
    )
