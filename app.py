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

        # 4. Built-in Direct DishTV LCN Map
        dishtv_lcn_map = {
            "star plus hd": "100", "star plus": "101", "zee tv hd": "102", "zee tv": "103",
            "sony entertainment television hd": "104", "sony entertainment television": "105",
            "sony sab hd": "106", "sony sab": "107", "&tv hd": "108", "dangal tv": "109",
            "star bharat hd": "115", "star bharat": "116", "investigation discovery": "119",
            "colors hd": "120", "colors": "121", "epic parivaar": "127", "sun neo": "128",
            "anmol tv": "135", "colors rishtey": "137", "sony pal": "138", "shemaroo tv": "139",
            "star utsav": "140", "dangal 2": "141", "zoom": "147", "dd national hd": "178",
            "dd rajasthan": "179", "dd up": "181", "dd mp": "183", "salaam tv": "203",
            "dd urdu": "213", "dd kashir": "215", "&pictures hd": "304", "&pictures": "305",
            "zee bollywood": "307", "watcho": "308", "sony max hd": "310", "sony max": "311",
            "colors cineplex hd": "312", "colors cineplex": "313", "zee cinema hd": "314",
            "zee cinema": "315", "star gold hd": "316", "star gold": "317",
            "star gold romance": "321", "star gold thrills": "329", "zee classic": "335",
            "sony max 2": "349", "star gold 2": "351", "colors cineplex superhits": "353",
            "anmol cinema 2": "354", "anmol cinema": "355", "goldmines": "359",
            "star gold select hd": "360", "star gold select": "361", "star utsav movies": "363",
            "shemaroo josh": "365", "sony wah": "375", "sony max 1": "380", "b4u kadak": "411",
            "big magic": "420", "zing": "451", "mtv hd": "454", "mtv": "455", "b4u music": "459",
            "9x m": "461", "epic music": "463", "colors infinity hd": "504", "colors infinity": "505",
            "disney international hd": "515", "mnx hd": "542", "mnx": "543", "sony pix hd": "544",
            "sony pix": "545", "movies now hd": "546", "movies now": "547", "star movies hd": "548",
            "star movies": "549", "romedy now": "563", "mn+ hd": "571", "star movies select hd": "573",
            "star movies select": "574", "star sports 1 hd": "602", "star sports 1": "603",
            "star sports 2 hd": "604", "star sports 2": "605", "star sports 1 hd hindi": "606",
            "star sports 1 hindi": "607", "sony sports ten 1 hd": "610", "sony sports ten 1": "611",
            "sony sports ten 2 hd": "612", "sony sports ten 2": "613", "sony sports ten 3 hindi hd": "614",
            "sony sports ten 3 hindi": "615", "sony sports ten 5 hd": "622", "sony sports ten 5": "623",
            "star sports 2 hindi hd": "624", "star sports 2 hindi": "625", "dd sports hd": "628",
            "eurosport hd": "629", "eurosport": "630", "unite8 sports 1 hd": "631", "unite8 sports 1": "632",
            "unite8 sports 2 hd": "633", "unite8 sports 2": "634", "dd sports": "638", "star sports khel": "640",
            "star sports 2 telugu": "641", "star sports 2 tamil": "642", "star sports select hd1": "645",
            "star sports select 1": "646", "star sports select hd2": "647", "star sports select 2": "648",
            "star sports 3": "649", "zee news": "651", "india tv": "653", "zee bharat": "654",
            "tv9 bharatvash": "658", "india daily 24x7": "662", "news18 india": "663", "times now navbharat": "666",
            "zee delhi ncr haryana": "670", "sudarshan tv": "679", "nation27": "690", "sansad tv 1 hd": "694",
            "sansad tv 2 hd": "696", "sansad tv 2": "697", "dd news hd": "698", "dd news": "699",
            "dd uttarakhand": "700", "news18 delhi ncr/j&k": "703", "jk 24x7 news": "704", "gulistan news": "705",
            "zee up uttrakhand": "707", "news state up/uk": "709", "news18 uttar pradesh/uttarakhand": "711",
            "news india 24x7": "713", "zee mp chattisgarh": "715", "news18 madhya pradesh/chhattisgarh": "717",
            "ibc 24": "720", "aaj tak": "725", "zee rajasthan news": "727", "news18 rajasthan": "728",
            "ndtv rajasthan": "729", "tv100": "730", "zee business": "731", "india news": "735",
            "abp news": "739", "republic bharat": "741", "news 24": "743", "bharat express": "753",
            "dd india hd": "754", "dd india": "759", "ndtv": "761", "india today": "763", "wion": "765",
            "times now world hd": "766", "times now": "767", "cnn news 18": "769", "mirror now": "773",
            "news x": "775", "cgtn": "785", "al jazeera": "787", "france 24": "790", "russia today": "792",
            "discovery hd world": "802", "discovery": "803", "animal planet hd world": "805", "animal planet": "806",
            "national geographic hd": "808", "national geographic channel": "809", "discovery science": "812",
            "discovery turbo": "814", "history tv 18": "820", "nat geo wild hd": "822", "zee bihar jharkhand": "823",
            "news18 bihar/jharkhand": "825", "sony bbc earth hd": "828", "sony bbc earth": "829", "epic tv": "830",
            "cnbc awaaz": "871", "zee zest": "903", "cnn intl": "911", "bbc world news": "913", "tlc hd world": "918",
            "tlc": "919", "travel xp hd": "920", "travelxp": "921", "cnbc tv18": "931", "et now": "933",
            "cnbc prime hd": "934", "pogo": "955", "history tv18 hd": "956", "sonic": "958", "epic": "959",
            "discovery kids": "960", "animal planet hd": "964", "nat geo wild": "968", "nick hd+": "974",
            "disney channel hd": "976", "disney channel": "977", "super hungama": "979", "epic kids": "980",
            "hungama tv": "981", "nick jr.": "987", "sony yay": "989", "etv bal bharat": "990", "divya tv": "1051",
            "sadhna tv": "1059", "hare krsna": "1061", "vedic": "1064", "satsang": "1065", "aastha bhajan": "1066",
            "sanskar": "1067", "aastha": "1077", "shubh tv": "1079", "sant wani": "1081", "shraddha mh one": "1083",
            "peace of mind": "1087", "shree disha bhakti": "1092", "sai leela": "1094", "jinvani": "1105",
            "nickelodeon": "1103", "paras gold one": "1110", "cartoon network": "1113", "disney jr.": "1123",
            "chardikla time tv": "1152", "ptc punjabi": "1154", "zee punjabi": "1156", "pitaara tv": "1181",
            "tabbar hits": "1182", "ptc chakde": "1183", "ptc punjabi gold": "1184", "9x tashan": "1185",
            "ptc music": "1186", "mh1": "1187", "balle balle": "1188", "zee punjab haryana himachal": "1190",
            "ptc news": "1191", "news18 punjab haryana himachal": "1193", "india news haryana": "1194",
            "ptc simran": "1195", "news state punjab haryana himachal": "1196", "khabrain abhi tak": "1197",
            "pratham news": "1200", "zee marathi hd": "1201", "zee marathi": "1202", "zee yuva": "1204",
            "star pravah hd": "1205", "star pravah": "1206", "colors marathi hd": "1208", "sony marathi": "1211",
            "shemaroo marathibana": "1212", "sun marathi": "1214", "aadinath": "1217", "zee talkies hd": "1230",
            "zee talkies": "1231", "pravah picture hd": "1232", "pravah picture": "1233", "9x jhakaas": "1243",
            "zee 24 taas": "1251", "abp majha": "1253", "namma homeopathy": "1254", "news18 marathi": "1255",
            "ndtv marathi": "1257", "tv9 marathi": "1259", "saam tv": "1261", "lokshahi": "1263",
            "pudhari news": "1265", "colors gujarati": "1272", "colors gujarati cinema": "1273",
            "news18 gujarati": "1289", "zee 24 kalak": "1291", "abp asmita": "1293", "sandesh news": "1296",
            "cnbc bajar": "1297", "vtv gujarati": "1298", "tv9 gujarati": "1299", "zee sarthak": "1302",
            "tarang": "1307", "star kiran": "1309", "sidharth tv": "1311", "dd oriya": "1325", "alankar": "1331",
            "sidharth gold": "1333", "tarang music": "1341", "otv": "1351", "kanak news": "1359",
            "prameya news7": "1363", "mbc tv": "1365", "argus": "1369", "sidharth utsav": "1395",
            "jay jagannath tv": "1397", "star jalsha hd": "1403", "star jalsha": "1404", "sony aath": "1407",
            "zee bangla hd": "1408", "colors bangla hd": "1410", "india daily live": "1414", "sun bangla": "1415",
            "enterr10 bangla": "1419", "rupasi bangla": "1427", "ctvn-akd-plus": "1428", "dd bangla": "1429",
            "jalsha movies hd": "1430", "zee bangla sonar": "1433", "colors bangla cinema": "1439",
            "fakt marathi": "1463", "kolkata tv": "1471", "news time": "1473", "24 ghanta tv": "1475",
            "abp ananda": "1477", "news18 bangla": "1479", "tv9 bangla": "1483", "calcutta news": "1489",
            "news live bangla": "1491", "rengoni tv": "1507", "rang": "1509", "jonack tv": "1511",
            "tv9 maharashtra": "1517", "dd assam": "1520", "prag news": "1525", "assam talk": "1527",
            "dy 365": "1529", "pratidin time": "1531", "news18 assam north east": "1533", "news live": "1535",
            "nepal one": "1537", "nb news": "1540", "bhojpuri cinema": "1554", "zee bioskope": "1555",
            "epic bhojpuri": "1556", "b4u bhojpuri": "1560", "dd bihar": "1565", "sangeet bhojpuri": "1573",
            "dd yadagiri": "1627", "dd saptagiri": "1629", "kalinga tv": "1755", "news18 oriya": "1765",
            "prarthana life": "1789", "colors bangla": "1809", "aakash aath": "1813", "rupashi bangla": "1815",
            "enter 10 bangla": "1821", "jalsha movies": "1835", "zee bangla cinema": "1837", "dhoom music": "1849",
            "sangeet bangla": "1851", "r. bangla": "1873", "dd arunprabha": "1914", "ramdhenu": "1979",
            "sun gemini hd": "2356", "sun gemini": "2357", "star maa hd": "2358", "star maa": "2359",
            "etv hd": "2360", "etv telugu": "2361", "zee telugu hd": "2362", "zee telugu": "2363",
            "etv plus": "2367", "vissa": "2369", "sun gemini life": "2371", "sun gemini comedy": "2379",
            "etv life": "2383", "maa gold": "2395", "sun gemini movies": "2397", "etv cinema": "2399",
            "maa movies hd": "2402", "maa movies": "2403", "zee cinemalu hd": "2404", "zee cinemalu": "2405",
            "sun gemini music": "2417", "maa music": "2419", "raj musix telugu": "2421", "etv music": "2423",
            "star sports 1 telugu hd": "2432", "star sports 1 telugu": "2433", "star sports 2 telugu hd": "2434",
            "sony sports ten 4 telugu": "2439", "tv5 telugu news": "2443", "etv andhra pradesh": "2445",
            "abn andhra jyothi": "2447", "sakshi tv": "2449", "etv telangana": "2451", "tv9 telugu news": "2453",
            "ntv news": "2455", "v6 news": "2457", "t news": "2459", "hm tv": "2461", "10tv telugu news": "2463",
            "raj news telugu": "2465", "zee telugu news": "2467", "khushi tv": "2487", "aradana": "2499",
            "svbc": "2503", "bhakti tv": "2505", "hindu dharmam": "2507", "sun udaya hd": "2606",
            "sun udaya": "2607", "zee kannada hd": "2608", "zee kannada": "2609", "star suvarna hd": "2610",
            "star suvarna": "2611", "colors kannada hd": "2616", "colors kannada": "2617", "colors super": "2619",
            "siri kannada-all time": "2621", "dd chandana": "2623", "sun udaya comedy": "2627", "star suvarna plus": "2639",
            "zee power": "2641", "sun udaya movies": "2643", "colors kannada cinema": "2647", "public movies": "2659",
            "sun udaya music": "2659", "raj musix kannada": "2661", "public music": "2663", "star sports 1 kannada": "2675",
            "star sports 2 kannada": "2677", "sony sports ten4 kannada": "2679", "suvarna news 24x7": "2683",
            "news18 kannada": "2685", "public tv": "2687", "news 1st": "2688", "tv9 kannada": "2689",
            "raj news kannada": "2691", "r. kannada": "2693", "power tv": "2696", "tv5 kannada": "2699",
            "ayush tv": "2713", "chintu tv": "2721", "puthu yugam": "2857", "sun tv hd": "2858", "sun tv": "2859",
            "vijay hd": "2860", "star vijay": "2861", "zee tamil hd": "2862", "zee tamil": "2863", "sun life": "2865",
            "jaya tv": "2867", "vijay super hd": "2868", "vijay super": "2869", "polimer tv": "2873",
            "sirippoli": "2875", "vasanth tv": "2877", "colors tamil hd": "2878", "colors tamil": "2879",
            "raj tv": "2881", "murasu tv": "2883", "kalaignar chithiram": "2885", "mega 24": "2891",
            "kalaignar tv": "2895", "adithya tv": "2897", "mega tv": "2899", "zee thirai": "2911", "ktv hd": "2912",
            "ktv": "2913", "j movies": "2915", "raj digital plus": "2917", "sun music hd": "2930",
            "sun music": "2931", "kalaignar isaiaruvi": "2933", "jaya max": "2935", "raj musix tamil": "2937",
            "mega musiq": "2939", "vijay takkar": "2941", "star sports 1 tamil hd": "2950",
            "star sports tamil 1": "2951", "sony sports ten 4 tamil": "2953", "star sports 2 tamil hd": "2954",
            "star sports 2 tamil": "2955", "raj news tamil": "2961", "sun news": "2963", "puthiya thalaimurai": "2965",
            "polimer news": "2967", "news 18 tamil nadu": "2968", "jaya plus": "2969", "malai murasu seithikal": "2970",
            "seithigal": "2971", "makkal tv": "2973", "sathiyam tv": "2975", "velicham tv": "2979",
            "news tamil 24x7": "2981", "d tamil": "2991", "kalvi tholaikkatchi": "2993", "chutti tv": "3001",
            "nambikkkai": "3013", "sai tv": "3015", "madha tv": "3017", "svbc 2": "3019", "jothi tv": "3025",
            "sun surya hd": "3106", "sun surya": "3107", "asianet hd": "3108", "asianet": "3109",
            "zee keralam hd": "3110", "zee keralam": "3111", "mazhavil manorama hd": "3112",
            "mazhavil manorama": "3113", "kairali": "3117", "asianet plus": "3119", "amrita tv": "3121",
            "we tv": "3123", "dd malayalam": "3125", "kaumudy": "3127", "flowers tv": "3133",
            "sun surya comedy": "3139", "sun surya movies": "3151", "asianet movies hd": "3152", "asianet movies": "3153",
            "sun surya music": "3165", "raj musix malayalam": "3167", "asianet news": "3179", "manorama news": "3181",
            "mathrubhumi news": "3183", "news 18 kerala": "3185", "raj news malayalam": "3187", "reporter tv": "3188",
            "kairali news": "3189", "news malayalam 24x7": "3190", "twenty-four": "3191", "janam tv": "3193",
            "media one": "3195", "jaihind tv": "3197", "safari tv": "3205", "kochu tv": "3215", "darshana tv": "3229",
            "shalom": "3231", "goodness tv": "3233", "powervision": "3235", "harvest tv": "3237",
            "teleshopping 1": "3999", "skyama daily post news": "4002", "north east live": "4004",
            "k news india": "4017", "manoranjan movies": "4029", "republic tv": "4043", "living india news": "4065"
        }

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
            clean_name = clean_and_filter_name(raw_na
