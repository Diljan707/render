from flask import Flask, Response
import requests
import re
import threading
import time

app = Flask(__name__)

cached_m3u = "#EXTM3U\n"
is_updating = False


# ==========================================
# FILTERS
# ==========================================

regional_langs = [
    "tamil",
    "telugu",
    "malayalam",
    "marathi",
    "bangla",
    "kannada",
    "gujarati",
    "odia"
]


def clean_and_filter_name(name):

    if not name:
        return None

    name = name.strip()
    low = name.lower()

    # Regional channels remove
    if any(
        re.search(
            rf"\b{re.escape(x)}\b",
            low
        )
        for x in regional_langs
    ):
        return None

    # Hindi remove
    name = re.sub(
        r"\s+Hindi\b",
        "",
        name,
        flags=re.IGNORECASE
    )

    # SD remove
    name = re.sub(
        r"\bSD\b",
        "",
        name,
        flags=re.IGNORECASE
    )

    # Extra spaces clean
    return re.sub(
        r"\s+",
        " ",
        name
    ).strip()


def normalize_name(name):

    cleaned = clean_and_filter_name(name)

    if not cleaned:
        return None

    return re.sub(
        r"[^a-z0-9]+",
        "",
        cleaned.lower()
    )


# ==========================================
# EXTRACT SECONDARY COMPLETE ENTRIES
# ==========================================

def get_secondary_streams():

    streams = {}

    try:

        url = (
            "https://raw.githubusercontent.com/"
            "Sflex0719/STBPLUS/refs/heads/main/Zio.m3u"
        )

        r = requests.get(
            url,
            timeout=10
        )

        if r.status_code != 200:

            print(
                "Zio.m3u fetch failed:",
                r.status_code
            )

            return streams


        entries = []
        current = []


        # ==================================
        # SPLIT M3U INTO COMPLETE ENTRIES
        # ==================================

        for line in r.text.splitlines():

            line = line.rstrip()

            if line.startswith("#EXTINF:"):

                if current:
                    entries.append(current)

                current = [line]

            elif current:

                current.append(line)


        if current:
            entries.append(current)


        # ==================================
        # CREATE SECONDARY MAP
        # ==================================

        for entry in entries:

            if not entry:
                continue

            extinf = entry[0]

            if "," not in extinf:
                continue


            raw_name = extinf.split(
                ",",
                1
            )[1].strip()


            # SAME FILTER AS PRIMARY
            clean_name = clean_and_filter_name(
                raw_name
            )

            if not clean_name:
                continue


            key = normalize_name(
                raw_name
            )

            if not key:
                continue


            # SAVE COMPLETE ORIGINAL ENTRY
            streams[key] = entry


        print(
            f"Secondary entries loaded: "
            f"{len(streams)}"
        )


    except Exception as e:

        print(
            "Secondary error:",
            e
        )


    return streams


# ==========================================
# RENAME SECONDARY
# ==========================================

def rename_secondary_entry(
    original_entry,
    primary_name,
    primary_logo
):

    entry = list(original_entry)


    for i, line in enumerate(entry):

        if (
            line.startswith("#EXTINF:")
            and "," in line
        ):

            prefix = line.split(
                ",",
                1
            )[0]


            # ==================================
            # PRIMARY LOGO
            # ==================================

            if primary_logo:

                if re.search(
                    r'tvg-logo="[^"]*"',
                    prefix,
                    flags=re.IGNORECASE
                ):

                    prefix = re.sub(
                        r'tvg-logo="[^"]*"',
                        f'tvg-logo="{primary_logo}"',
                        prefix,
                        flags=re.IGNORECASE
                    )

                else:

                    # If secondary has no tvg-logo,
                    # add primary logo
                    prefix += (
                        f' tvg-logo="{primary_logo}"'
                    )


            # ==================================
            # ONLY NAME CHANGES
            # ==================================

            entry[i] = (
                f"{prefix},{primary_name}"
            )

            break


    # ==================================
    # EVERYTHING ELSE ORIGINAL
    # ==================================

    return "\n".join(entry)


# ==========================================
# FIND SECONDARY MATCH
# ==========================================

def find_secondary(
    secondary_streams,
    match_name,
    clean_name
):

    # ==================================
    # EXACT NORMALIZED MATCH
    # ==================================

    if match_name in secondary_streams:

        return secondary_streams[
            match_name
        ]


    # ==================================
    # CLEAN NAME MATCH
    # ==================================

    clean_key = re.sub(
        r"[^a-z0-9]+",
        "",
        clean_name.lower()
    )


    if clean_key in secondary_streams:

        return secondary_streams[
            clean_key
        ]


    # ==================================
    # FUZZY MATCH
    # ==================================

    for key, entry in secondary_streams.items():

        if (
            match_name in key
            or key in match_name
            or clean_key in key
            or key in clean_key
        ):

            return entry


    return None


# ==========================================
# PRIMARY CHANNELS
# ==========================================

def get_primary_channels():

    url = (
        "https://jjtvxweb.pages.dev/"
        "jstr4web.json"
    )


    r = requests.get(
        url,
        timeout=10
    )


    r.raise_for_status()


    return r.json()


# ==========================================
# BUILD PLAYLIST
# ==========================================

def update_m3u_background():

    global cached_m3u
    global is_updating


    if is_updating:
        return


    is_updating = True


    try:

        print(
            "Updating playlist..."
        )


        # ==================================
        # LOAD PRIMARY
        # ==================================

        primary_channels = (
            get_primary_channels()
        )


        # ==================================
        # LOAD SECONDARY
        # ==================================

        secondary_streams = (
            get_secondary_streams()
        )


        m3u = "#EXTM3U\n"


        primary_count = 0
        secondary_count = 0


        # ==================================
        # PRIMARY LOOP
        # ==================================

        for ch in primary_channels:


            # ==================================
            # PRIMARY NAME
            # ==================================

            raw_name = ch.get(
                "name",
                "Unknown"
            )


            # ==================================
            # PRIMARY URL
            # ==================================

            primary_url = ch.get(
                "url",
                ""
            )


            if not primary_url:
                continue


            # ==================================
            # PRIMARY FILTER
            # ==================================

            clean_name = (
                clean_and_filter_name(
                    raw_name
                )
            )


            if not clean_name:
                continue


            # ==================================
            # NORMALIZED NAME
            # ==================================

            match_name = (
                normalize_name(
                    raw_name
                )
            )


            if not match_name:
                continue


            # ==================================
            # PRIMARY ID
            # ==================================

            ch_id = str(
                ch.get(
                    "id",
                    ""
                )
            )


            # ==================================
            # PRIMARY LOGO
            # ==================================

            logo = ch.get(
                "logo",
                ""
            )


            # ==================================
            # CATEGORY
            # ==================================

            category = ch.get(
                "category",
                "Unknown"
            )


            # ==================================
            # GROUP
            # ==================================

            group = (
                f"JioTV+ ▶ | {category}"
            )


            # ==================================
            # PRIMARY ENTRY
            # ==================================

            m3u += (
                f'#EXTINF:-1 '
                f'tvg-id="{ch_id}" '
                f'tvg-logo="{logo}" '
                f'group-title="{group}",'
                f'{clean_name}\n'
            )


            m3u += (
                f"{primary_url}\n\n"
            )


            primary_count += 1


            # ==================================
            # SECONDARY MATCH
            # ==================================

            secondary_entry = find_secondary(
                secondary_streams,
                match_name,
                clean_name
            )


            if secondary_entry:


                # ==================================
                # SECONDARY:
                #
                # ORIGINAL EVERYTHING
                # ONLY:
                # NAME = PRIMARY NAME
                # LOGO = PRIMARY LOGO
                # ==================================

                renamed_entry = (
                    rename_secondary_entry(
                        secondary_entry,
                        clean_name,
                        logo
                    )
                )


                m3u += (
                    renamed_entry
                    + "\n\n"
                )


                secondary_count += 1


        # ==================================
        # CACHE
        # ==================================

        cached_m3u = m3u


        print(
            "================================"
        )


        print(
            "Playlist update complete"
        )


        print(
            f"Primary: {primary_count}"
        )


        print(
            f"Secondary: {secondary_count}"
        )


        print(
            "================================"
        )


    except Exception as e:

        print(
            "Update error:",
            e
        )


    finally:

        is_updating = False


# ==========================================
# AUTO UPDATE
# ==========================================

def periodic_updater():

    while True:

        update_m3u_background()

        # ==================================
        # UPDATE EVERY 3 MINUTES
        # ==================================

        time.sleep(180)


# ==========================================
# FIRST UPDATE
# ==========================================

update_m3u_background()


threading.Thread(
    target=periodic_updater,
    daemon=True
).start()


# ==========================================
# HOME
# ==========================================

@app.route("/")
def home():

    return (
        "Primary + Secondary "
        "M3U Server Running"
    )


# ==========================================
# PLAYLIST
# ==========================================

@app.route("/playlist.m3u")
def playlist():

    return Response(
        cached_m3u,
        mimetype="audio/x-mpegurl"
    )


# ==========================================
# START SERVER
# ==========================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=10000
    )
