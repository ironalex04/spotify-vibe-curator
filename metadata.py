import os
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

LASTFM_API_ENDPOINT = "http://ws.audioscrobbler.com/2.0/"

class LastFMClient:
    """Manages requests to the Last.fm API to fetch track-level metadata and tags."""

    def __init__(self, api_key: str = None):
        """Initializes the Last.fm client with an API key, falling back to environment variables.
        
        Args:
            api_key: Last.fm API key.
        """
        self.api_key = api_key or os.getenv("LASTFM_API_KEY")
        self._validate_credentials()

    def _validate_credentials(self):
        """Validates that the API key is configured."""
        if not self.api_key or self.api_key == "your_lastfm_api_key_here":
            raise ValueError(
                "Missing Last.fm configuration credentials: LASTFM_API_KEY. "
                "Please configure this in your environment or a .env file."
            )

    def get_track_tags(self, artist: str, track_title: str, limit: int = 15) -> list:
        """Fetches top user tags for a specific track from Last.fm.
        
        Args:
            artist: The artist name.
            track_title: The title of the track.
            limit: The maximum number of tags to return. Defaults to 15.
            
        Returns:
            list: A list of tag dictionaries containing 'name' and 'count'.
                 Returns an empty list if track is not found or has no tags.
        """
        params = {
            "method": "track.getTopTags",
            "artist": artist,
            "track": track_title,
            "api_key": self.api_key,
            "format": "json"
        }
        
        try:
            response = requests.get(LASTFM_API_ENDPOINT, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # Check for error in JSON response
            if "error" in data:
                print(f"Last.fm API warning: {data.get('message', 'Unknown error')}")
                return []
                
            toptags = data.get("toptags", {})
            raw_tags = toptags.get("tag", [])
            
            # Last.fm API returns a single dictionary instead of a list if there is only 1 tag
            if isinstance(raw_tags, dict):
                raw_tags = [raw_tags]
                
            # Extract and format the tags
            tags = []
            for tag in raw_tags[:limit]:
                name = tag.get("name")
                # Last.fm returns count as integer or string representing integer, convert safely
                try:
                    count = int(tag.get("count", 0))
                except (ValueError, TypeError):
                    count = 0
                if name:
                    tags.append({"name": name.lower().strip(), "count": count})
            return tags
            
        except requests.RequestException as e:
            print(f"Network error communicating with Last.fm: {e}")
            return []
        except (ValueError, KeyError, TypeError) as e:
            print(f"Error parsing Last.fm API response: {e}")
            return []

if __name__ == "__main__":
    print("Testing Last.fm API Client initialization...")
    try:
        client = LastFMClient()
        print("Success: Last.fm client initialized. API key is set.")
    except ValueError as e:
        print(f"Configuration validation failed: {e}")
        print("Please check your .env configuration.")
