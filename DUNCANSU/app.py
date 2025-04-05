from flask import Flask, request, jsonify, render_template, redirect
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import re
import time

app = Flask(__name__)

# Global User-Agent and base URL
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
base_url = 'https://streamed.su/api'

# Helper function to fetch matches by sport
def get_matches(sport=None, popular=False, live=False, today=False):
    headers = {'User-Agent': UA}
    url = f"{base_url}/matches/"
    
    if sport:
        url += sport
    else:
        url += "all"

    if popular:
        url += "/popular"
    elif live:
        url += "/live"
    elif today:
        url += "/all-today"

    try:
        response = requests.get(url, headers=headers, timeout=10)
        matches = response.json()
    except Exception as e:
        print(f"Error fetching matches: {e}")
        return []

    return matches

# Helper function to fetch sports categories
def get_sports():
    headers = {'User-Agent': UA}
    url = f"{base_url}/sports"
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        sports = response.json()
    except Exception as e:
        print(f"Error fetching sports: {e}")
        return []

    return sports

@app.route('/play/<event_name>', methods=['GET', 'POST'])
def play_stream(event_name):
    print(f"Received request to play: {event_name}")
    
    # Use the original m3u8 playlist URL
    m3u_playlist_url = 'https://proxy.miniduncan.net/playlist?url=https%3A%2F%2Fbit.ly%2Fsu-m3u1&data=UmVmZXJlcj1odHRwczovL2VtYmVkbWUudG9wLw%3D%3D&epgMerging=true'
    
    try:
        print("Fetching m3u content...")  # Indicate that we're fetching the m3u
        response = requests.get(m3u_playlist_url)
        m3u_content = response.text
        
        # Log the m3u content for debugging purposes
        print("Fetched m3u content:", m3u_content[:500])  # Limiting the log to the first 500 characters
        
        # Find the top 4 stream URLs for the event
        stream_urls = find_stream_urls(m3u_content, event_name)
        
        if stream_urls:
            print(f"Found stream URLs for {event_name}: {stream_urls}")
            
            # Create a dictionary mapping "STREAM X" to the actual URLs
            obfuscated_streams = {f"STREAM {i+1}": url for i, url in enumerate(stream_urls[:4])}
            
            # If the request method is POST, play the selected stream
            if request.method == 'POST':
                selected_url = request.form['stream_url']
                return render_template('player_embed.html', m3u_url=selected_url)
            
            # Show the dropdown with the obfuscated stream names
            return render_template('select_stream.html', event_name=event_name, obfuscated_streams=obfuscated_streams)
        else:
            print(f"No stream found for {event_name}")
            return f"No stream found for {event_name}", 404

    except Exception as e:
        print(f"Error fetching the m3u playlist: {e}")
        return "Error fetching playlist", 500



# Helper function to find the stream URL from the m3u content
import difflib
import re

def find_stream_urls(m3u_content, event_name):
    """
    Search the m3u content for the given event name (tvg-name) and return the top 4 closest stream URLs.
    If no exact match is found, look for keyword matches with improved matching.
    """
    pattern = re.compile(r'#EXTINF:-1 .*tvg-name="([^"]+).*",(.+)\n(.+)')
    
    # Store all matches in a list to iterate multiple times
    matches = list(pattern.finditer(m3u_content))

    # List to hold (score, stream_url) tuples
    match_scores = []

    # Try to match the exact event name first
    for match in matches:
        tvg_name = match.group(2).strip()
        stream_url = match.group(3).strip()
        
        # Check if the event name matches exactly (case-insensitive)
        exact_match_score = difflib.SequenceMatcher(None, event_name.lower(), tvg_name.lower()).ratio()
        if exact_match_score > 0.8:  # You can adjust this threshold as needed
            match_scores.append((exact_match_score, stream_url))

    # If no exact match, try to find keyword matches with improved logic
    if not match_scores:
        best_match_score = 0
        ignore_keywords = ["vs", "v", "at", "women", "men", "live"]
        event_keywords = [word for word in event_name.split() if word.lower() not in ignore_keywords]

        for match in matches:
            tvg_name = match.group(2).strip()
            stream_url = match.group(3).strip()

            # Score the tvg_name based on how many relevant keywords from event_name it contains
            match_score = sum(1 for keyword in event_keywords if keyword.lower() in tvg_name.lower())

            # Use fuzzy matching for remaining score improvements
            fuzzy_score = difflib.SequenceMatcher(None, event_name.lower(), tvg_name.lower()).ratio()
            match_score += fuzzy_score * 0.5  # Adjust the weight of fuzzy matching as needed

            # Append the match score and stream URL to the list
            match_scores.append((match_score, stream_url))

    # Sort the match scores in descending order and return the top 4 matches
    match_scores.sort(reverse=True, key=lambda x: x[0])

    # Return the top 4 stream URLs (or less if fewer matches are found)
    return [url for _, url in match_scores[:4]]

    
    
# Main menu route
@app.route('/')
def main_menu():
    menu = [
        {'title': 'ALL SPORTS STREAMS', 'url': '/schedule'},
    ]
    return render_template('menu.html', menu=menu)

# Schedule route to show categories
@app.route('/schedule')
def schedule():
    sports = get_sports()
    return render_template('schedule.html', sports=sports)

# Matches for a specific sport
@app.route('/matches/<sport>')
def matches(sport):
    matches = get_matches(sport=sport)
    
    # Only filter out matches with no posters if the sport is "football"
    if sport.lower() == 'football':
        matches = [
            match for match in matches
            if match.get('poster') and match['poster'] != '/'
        ]

    return render_template('channels.html', categ=sport, events=matches)



# Today's matches
@app.route('/matches/today')
def matches_today():
    matches = get_matches(today=True)
    return render_template('channels.html', categ="Today's Matches", events=matches)

# Live matches
@app.route('/matches/live')
def live_matches():
    matches = get_matches(live=True)
    return render_template('channels.html', categ="Live Matches", events=matches)

@app.route('/livetv')
def live_tv():
    # Manually define the list of channels
    channels = [
        {
            'name': 'Sky Sports Main Event',
            'logo': 'https://i0.wp.com/afcdonscast.co.uk/wp-content/uploads/2022/07/sky-sports-main-event-1.webp?ssl=1',
            'url': 'https://proxy.miniduncan.net?url=https%3A%2F%2Fxyzdddd.mizhls.ru%2Flb%2Fpremium38%2Findex.m3u8%0D&data=UmVmZXJlcj1odHRwczovL2Nvb2tpZXdlYnBsYXkueHl6L3xPcmlnaW49aHR0cHM6Ly9jb29raWV3ZWJwbGF5Lnh5enxVc2VyLUFnZW50PU1vemlsbGEvNS4wIChYMTE7IExpbnV4IHg4Nl82NCkgQXBwbGVXZWJLaXQvNTM3LjM2IChLSFRNTCwgbGlrZSBHZWNrbykgQ2hyb21lLzEyOS4wLjAuMCBTYWZhcmkvNTM3LjM2'
        },
        {
            "name": "Sky Sports Premier League",
            "logo": "https://protvmovies.com/uploads/cache/channel_thumb/uploads/png/77cf85caadd922cc61697d02da40b60e.png",
            "url": "https://proxy.miniduncan.net?url=https%3A%2F%2Fxyzdddd.mizhls.ru%2Flb%2Fpremium130%2Findex.m3u8%0D&data=UmVmZXJlcj1odHRwczovL2Nvb2tpZXdlYnBsYXkueHl6L3xPcmlnaW49aHR0cHM6Ly9jb29raWV3ZWJwbGF5Lnh5enxVc2VyLUFnZW50PU1vemlsbGEvNS4wIChYMTE7IExpbnV4IHg4Nl82NCkgQXBwbGVXZWJLaXQvNTM3LjM2IChLSFRNTCwgbGlrZSBHZWNrbykgQ2hyb21lLzEyOS4wLjAuMCBTYWZhcmkvNTM3LjM2"
        },
        {
            "name": "TNT Sports 1",
            "logo": "https://www.sportspromedia.com/wp-content/uploads/2023/08/tnt-sports-logo-transparent.png",
            "url": "https://proxy.miniduncan.net?url=https%3A%2F%2Fxyzdddd.mizhls.ru%2Flb%2Fpremium31%2Findex.m3u8%0D&data=UmVmZXJlcj1odHRwczovL2Nvb2tpZXdlYnBsYXkueHl6L3xPcmlnaW49aHR0cHM6Ly9jb29raWV3ZWJwbGF5Lnh5enxVc2VyLUFnZW50PU1vemlsbGEvNS4wIChYMTE7IExpbnV4IHg4Nl82NCkgQXBwbGVXZWJLaXQvNTM3LjM2IChLSFRNTCwgbGlrZSBHZWNrbykgQ2hyb21lLzEyOS4wLjAuMCBTYWZhcmkvNTM3LjM2"
        },
                {
            'name': 'LFC TV',
            'logo': 'https://upload.wikimedia.org/wikipedia/en/thumb/1/1f/LFC_TV_logo.png/250px-LFC_TV_logo.png',
            'url': 'https://proxy.miniduncan.net?url=https%3A%2F%2Fxyzdddd.mizhls.ru%2Flb%2Fpremium826%2Findex.m3u8%0D&data=UmVmZXJlcj1odHRwczovL2Nvb2tpZXdlYnBsYXkueHl6L3xPcmlnaW49aHR0cHM6Ly9jb29raWV3ZWJwbGF5Lnh5enxVc2VyLUFnZW50PU1vemlsbGEvNS4wIChYMTE7IExpbnV4IHg4Nl82NCkgQXBwbGVXZWJLaXQvNTM3LjM2IChLSFRNTCwgbGlrZSBHZWNrbykgQ2hyb21lLzEyOS4wLjAuMCBTYWZhcmkvNTM3LjM2'
        },
        {
            "name": "Optus Sport",
            "logo": "https://i.ibb.co/pJ35XHx/sport-optus-com-au-1.png",
            "url": "https://proxy.miniduncan.net?url=https%3A%2F%2Fxyzdddd.mizhls.ru%2Flb%2Fpremium13%2Findex.m3u8%0D&data=UmVmZXJlcj1odHRwczovL2Nvb2tpZXdlYnBsYXkueHl6L3xPcmlnaW49aHR0cHM6Ly9jb29raWV3ZWJwbGF5Lnh5enxVc2VyLUFnZW50PU1vemlsbGEvNS4wIChYMTE7IExpbnV4IHg4Nl82NCkgQXBwbGVXZWJLaXQvNTM3LjM2IChLSFRNTCwgbGlrZSBHZWNrbykgQ2hyb21lLzEyOS4wLjAuMCBTYWZhcmkvNTM3LjM2"
        },
        {
            "name": "Hub Premier 1",
            "logo": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTJoebLmPg9x3k7wWEqnStrsGax8HjE4Wq03Q&s",
            "url": "https://proxy.miniduncan.net?url=https%3A%2F%2Fxyzdddd.mizhls.ru%2Flb%2Fpremium4%2Findex.m3u8%0D&data=UmVmZXJlcj1odHRwczovL2Nvb2tpZXdlYnBsYXkueHl6L3xPcmlnaW49aHR0cHM6Ly9jb29raWV3ZWJwbGF5Lnh5enxVc2VyLUFnZW50PU1vemlsbGEvNS4wIChYMTE7IExpbnV4IHg4Nl82NCkgQXBwbGVXZWJLaXQvNTM3LjM2IChLSFRNTCwgbGlrZSBHZWNrbykgQ2hyb21lLzEyOS4wLjAuMCBTYWZhcmkvNTM3LjM2"
        },
        {
            "name": "USA Network",
            "logo": "https://upload.wikimedia.org/wikipedia/commons/d/d7/USA_Network_logo_%282016%29.svg",
            "url": "https://proxy.miniduncan.net?url=https%3A%2F%2Fxyzdddd.mizhls.ru%2Flb%2Fpremium343%2Findex.m3u8%0D&data=UmVmZXJlcj1odHRwczovL2Nvb2tpZXdlYnBsYXkueHl6L3xPcmlnaW49aHR0cHM6Ly9jb29raWV3ZWJwbGF5Lnh5enxVc2VyLUFnZW50PU1vemlsbGEvNS4wIChYMTE7IExpbnV4IHg4Nl82NCkgQXBwbGVXZWJLaXQvNTM3LjM2IChLSFRNTCwgbGlrZSBHZWNrbykgQ2hyb21lLzEyOS4wLjAuMCBTYWZhcmkvNTM3LjM2"
        },
        # Add more channels as needed
    ]
    
    
    return render_template('livetv.html', channels=channels)

# List of providers (base URLs)
providers = [
    "https://myvip.global.ssl.fastly.net",
    "https://fs.anonup.net",
    "https://fs.fscdn.fun",
    "https://dc.vipstreams.in"
]

# Utility function to check if a URL is reachable
def check_url(full_url):
    session = requests.Session()
    try:
        response = session.head(full_url, timeout=0.3)  # Use 1-second timeout
        return full_url if response.status_code == 200 else None
    except requests.RequestException:
        return None

def find_valid_urls(channel_list):
    # Generate full URLs for all channels and providers
    full_urls = [
        (channel, f"{provider}{channel['url']}") 
        for channel in channel_list 
        for provider in providers
    ]
    # Check URLs in parallel
    valid_urls = {}
    with ThreadPoolExecutor(max_workers=20) as executor:  # Adjust max_workers based on your server's capability
        future_to_channel = {executor.submit(check_url, url): (channel, url) for channel, url in full_urls}
        for future in as_completed(future_to_channel):
            channel, url = future_to_channel[future]
            if future.result():  # If a valid URL is found
                if channel["url"] not in valid_urls:
                    valid_urls[channel["url"]] = url
    return valid_urls

@app.route('/ppvland')
def ppv_land():
    # Manually define the list of channels with relative paths
    channels = [
        {
            'name': 'Manchester United vs Newcastle',
            'logo': 'https://protvmovies.com/uploads/cache/channel_thumb/uploads/png/77cf85caadd922cc61697d02da40b60e.png',
            'url': '/epl1/index.m3u8'
        },
        # Add more channels as needed
    ]

    # Find valid URLs for channels
    valid_urls = find_valid_urls(channels)

    # Update channel URLs
    for channel in channels:
        channel["url"] = valid_urls.get(channel["url"], None)

    # Filter out channels with no valid URLs
    channels = [channel for channel in channels if channel["url"]]

    return render_template('livetv.html', channels=channels)

@app.route('/play/<path:stream_url>')
def live_tv_play(stream_url):
    """
    Route to play a specific stream URL from the Live TV playlist.
    """
    stream_url = f"https://{stream_url}" if not stream_url.startswith('https') else stream_url
    return render_template('player_embed.html', m3u_url=stream_url)

# Live matches
@app.route('/matches/ppvland')
def ppvland():
    return render_template('ppvland.html')


# Cache structure to store data and timestamps
cache = {
    "all_streams": {"data": None, "timestamp": 0},
    "stream_details": {}  # This will store cached details for specific stream IDs
}

CACHE_TIMEOUT = 300  # 5 minutes in seconds

@app.route('/proxy/streams/', methods=['GET'])
@app.route('/proxy/streams/<id>', methods=['GET'])  # Handles dynamic IDs
def proxy_streams(id=None):
    try:
        headers = {"X-FS-Client": "FS WebClient 1.0"}
        current_time = time.time()
        
        if id:
            # If an ID is provided, fetch details for that specific stream
            if id in cache["stream_details"]:
                cached_entry = cache["stream_details"][id]
                if current_time - cached_entry["timestamp"] < CACHE_TIMEOUT:
                    # Return cached data if within timeout
                    return jsonify(cached_entry["data"])

            # Fetch new data if cache is expired or not present
            response = requests.get(f'https://ppv.wtf/api/streams/{id}', headers=headers)
            response.raise_for_status()  # Ensure we handle errors from requests
            data = response.json()
            
            # Update cache
            cache["stream_details"][id] = {"data": data, "timestamp": current_time}
            return jsonify(data)
        else:
            # If no ID is provided, fetch all streams
            if current_time - cache["all_streams"]["timestamp"] < CACHE_TIMEOUT:
                # Return cached data if within timeout
                return jsonify(cache["all_streams"]["data"])

            # Fetch new data if cache is expired or not present
            response = requests.get('https://ppv.wtf/api/streams', headers=headers)
            response.raise_for_status()  # Ensure we handle errors from requests
            data = response.json()
            
            # Update cache
            cache["all_streams"] = {"data": data, "timestamp": current_time}
            return jsonify(data)
    
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
