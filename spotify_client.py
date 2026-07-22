import os
import time
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

DEFAULT_SCOPES = [
    "playlist-read-private",
    "playlist-read-collaborative",
    "playlist-modify-public",
    "playlist-modify-private",
    "user-library-read"
]

class SpotifyClientManager:
    """Manages connection and OAuth authentication to the Spotify Web API using spotipy."""
    
    def __init__(self, client_id: str = None, client_secret: str = None, redirect_uri: str = None, scope: str = None):
        """Initializes the manager with credentials, falling back to environment variables.
        
        Args:
            client_id: Spotify Client ID.
            client_secret: Spotify Client Secret.
            redirect_uri: Spotify Redirect URI.
            scope: String or list of scopes to request. Defaults to DEFAULT_SCOPES.
        """
        self.client_id = client_id or os.getenv("SPOTIPY_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("SPOTIPY_CLIENT_SECRET")
        self.redirect_uri = redirect_uri or os.getenv("SPOTIPY_REDIRECT_URI")
        
        if isinstance(scope, list):
            self.scope = " ".join(scope)
        elif isinstance(scope, str):
            self.scope = scope
        else:
            self.scope = " ".join(DEFAULT_SCOPES)
            
        self._validate_credentials()
        self._sp = None

    def _validate_credentials(self):
        """Validates that credentials are not empty or missing."""
        missing = []
        if not self.client_id:
            missing.append("SPOTIPY_CLIENT_ID")
        if not self.client_secret:
            missing.append("SPOTIPY_CLIENT_SECRET")
        if not self.redirect_uri:
            missing.append("SPOTIPY_REDIRECT_URI")
            
        if missing:
            raise ValueError(
                f"Missing Spotify configuration credentials: {', '.join(missing)}. "
                "Please configure them in your environment or a .env file."
            )

    def get_client(self) -> spotipy.Spotify:
        """Initializes and returns the authenticated spotipy.Spotify client.
        
        Returns:
            spotipy.Spotify: The authenticated client.
        """
        if self._sp is None:
            # SpotifyOAuth handles token generation, refresh, and storage automatically
            auth_manager = SpotifyOAuth(
                client_id=self.client_id,
                client_secret=self.client_secret,
                redirect_uri=self.redirect_uri,
                scope=self.scope,
                open_browser=True
            )
            self._sp = spotipy.Spotify(auth_manager=auth_manager)
        return self._sp

    def _execute_with_retry(self, func, *args, **kwargs):
        """Executes a spotipy client function and retries automatically if rate limited (HTTP 429)."""
        import time
        from spotipy.exceptions import SpotifyException
        
        max_retries = 5
        retry_count = 0
        while retry_count < max_retries:
            try:
                return func(*args, **kwargs)
            except SpotifyException as e:
                if e.http_status == 429:
                    # If Spotify returns Retry-After header, use it, else default to 2 seconds
                    retry_after = int(e.headers.get("Retry-After", 2))
                    print(f"\n[Rate Limit] Spotify API rate limit reached. Waiting {retry_after}s before retrying...")
                    time.sleep(retry_after)
                    retry_count += 1
                else:
                    raise e
        return func(*args, **kwargs)

    def verify_connection(self) -> dict:
        """Verifies connectivity by fetching the authenticated user's profile.
        
        Returns:
            dict: The current user's profile information if successful.
        Raises:
            spotipy.SpotifyException: If authentication or API request fails.
        """
        client = self.get_client()
        user_info = self._execute_with_retry(client.current_user)
        return user_info

    def get_user_playlists(self) -> list:
        """Fetches all playlists of the authenticated user.
        
        Returns:
            list: List of playlist items.
        """
        client = self.get_client()
        playlists = []
        results = self._execute_with_retry(client.current_user_playlists, limit=50)
        while results:
            playlists.extend(results['items'])
            print(f"  Fetched {len(playlists)} playlists...", end="\r")
            if results['next']:
                results = self._execute_with_retry(client.next, results)
            else:
                results = None
        print(f"  Fetched {len(playlists)} playlists total.      ")
        return playlists

    def find_or_create_playlist(self, name: str, description: str = "", public: bool = False) -> str:
        """Finds a playlist by name, or creates a new one if it doesn't exist.
        
        Args:
            name: The name of the playlist to find or create.
            description: The description for the new playlist.
            public: Whether the playlist should be public. Defaults to False.
            
        Returns:
            str: The playlist ID.
        """
        client = self.get_client()
        user_id = self.verify_connection()['id']
        
        playlists = self.get_user_playlists()
        for pl in playlists:
            if pl['name'] == name:
                return pl['id']
                
        new_pl = self._execute_with_retry(
            client.user_playlist_create,
            user=user_id,
            name=name,
            public=public,
            description=description
        )
        return new_pl['id']

    def get_all_saved_tracks(self) -> list:
        """Fetches all saved tracks (Liked Songs) from the user's library.
        
        Returns:
            list: List of track URIs.
        """
        client = self.get_client()
        tracks = []
        results = self._execute_with_retry(client.current_user_saved_tracks, limit=50)
        while results:
            for item in results['items']:
                track = item['track']
                if track:
                    tracks.append(track['uri'])
            print(f"  Fetched {len(tracks)} Liked Songs...", end="\r")
            if results['next']:
                results = self._execute_with_retry(client.next, results)
            else:
                results = None
        print(f"  Fetched {len(tracks)} Liked Songs total.      ")
        return tracks

    def get_playlist_tracks(self, playlist_id: str, playlist_name: str = "Playlist") -> list:
        """Fetches all track URIs currently in a playlist.
        
        Args:
            playlist_id: The ID of the playlist.
            playlist_name: The name of the playlist for logs.
            
        Returns:
            list: List of track URIs.
        """
        client = self.get_client()
        tracks = []
        results = self._execute_with_retry(client.playlist_tracks, playlist_id, fields="items,next", limit=100)
        while results:
            for item in results['items']:
                track_data = item.get('track') or item.get('item')
                if track_data and isinstance(track_data, dict) and track_data.get('uri'):
                    tracks.append(track_data['uri'])
            if results['next']:
                print(f"  Querying {playlist_name} (loaded {len(tracks)} songs)...", end="\r")
                results = self._execute_with_retry(client.next, results)
            else:
                results = None
        return tracks

    def get_playlist_tracks_detailed(self, playlist_id: str, playlist_name: str = "Playlist") -> list:
        """Fetches detailed track info (uri, title, artist) for all tracks in a playlist.
        
        Args:
            playlist_id: The ID of the playlist.
            playlist_name: The name of the playlist for logs.
            
        Returns:
            list: List of dicts, each with 'uri', 'title', and 'artist'.
        """
        client = self.get_client()
        tracks = []
        results = self._execute_with_retry(client.playlist_tracks, playlist_id, fields="items,next", limit=100)
        while results:
            for item in results['items']:
                track_data = item.get('track') or item.get('item')
                if track_data and isinstance(track_data, dict) and track_data.get('uri'):
                    artists = track_data.get('artists', [])
                    artist_name = artists[0].get('name', 'Unknown Artist') if artists else 'Unknown Artist'
                    tracks.append({
                        "uri": track_data['uri'],
                        "title": track_data.get('name', 'Unknown Track'),
                        "artist": artist_name
                    })
            if results['next']:
                print(f"  Querying {playlist_name} (loaded {len(tracks)} songs)...", end="\r")
                results = self._execute_with_retry(client.next, results)
            else:
                results = None
        return tracks

    def deduplicate_playlist(self, playlist_id: str) -> int:
        """Scans a playlist for duplicate tracks and removes them, leaving exactly one of each.
        
        Args:
            playlist_id: The ID of the playlist to deduplicate.
            
        Returns:
            int: The number of duplicate tracks cleaned up.
        """
        client = self.get_client()
        tracks = self.get_playlist_tracks(playlist_id, "::seed")
        
        counts = {}
        for t in tracks:
            counts[t] = counts.get(t, 0) + 1
            
        duplicates = [uri for uri, count in counts.items() if count > 1]
        
        if not duplicates:
            return 0
            
        print(f"  Found {len(duplicates)} duplicate tracks in '::seed'. Cleaning them up...")
        
        for i in range(0, len(duplicates), 100):
            batch = duplicates[i:i+100]
            self._execute_with_retry(client.playlist_remove_all_occurrences_of_items, playlist_id, batch)
            self._execute_with_retry(client.playlist_add_items, playlist_id, batch)
            
        return len(duplicates)

    def sync_library_to_seed(self) -> dict:
        """Syncs all saved tracks (Liked Songs) and tracks from all playlists 
        (except '::seed') to a playlist named '::seed'.
        
        Finds or creates the playlist. Compares existing tracks in the playlist
        with all library and playlist tracks to only add missing ones.
        
        Returns:
            dict: Sync statistics.
        """
        client = self.get_client()
        
        print("Finding or creating '::seed' playlist...")
        playlist_id = self.find_or_create_playlist(
            name="::seed",
            description="Inbox/Seed playlist for Spotify Vibe Curator. Automatically synced from Liked Songs and playlists.",
            public=False
        )
        
        print("Fetching existing tracks in '::seed'...")
        existing_tracks = set(self.get_playlist_tracks(playlist_id, "::seed"))
        print(f"Found {len(existing_tracks)} tracks already in '::seed'.")
        
        print("\nFetching all Liked Songs from your library...")
        library_tracks = self.get_all_saved_tracks()
        
        print("\nFetching your playlists list...")
        playlists = self.get_user_playlists()
        
        print("\nScanning tracks from all playlists (this may take a moment)...")
        all_playlist_tracks = []
        for pl in playlists:
            if pl['id'] == playlist_id or pl['name'] == "::seed":
                continue
            
            try:
                tracks = self.get_playlist_tracks(pl['id'], pl['name'])
                all_playlist_tracks.extend(tracks)
                import time
                time.sleep(0.05) # Tiny proactive throttle to prevent rate limit
            except Exception as e:
                print(f"\nWarning: Failed to fetch tracks for playlist {pl['name']} ({pl['id']}): {e}")
        
        print(f"\nScanned {len(all_playlist_tracks)} tracks from your playlists.")
        
        combined_tracks = set(library_tracks + all_playlist_tracks)
        missing_tracks = [t for t in combined_tracks if t not in existing_tracks]
        
        total_missing = len(missing_tracks)
        print(f"\nUnique candidate tracks found: {len(combined_tracks)}")
        print(f"Tracks to add to '::seed': {total_missing}")
        
        added_count = 0
        if missing_tracks:
            print("Adding tracks to '::seed'...")
            for i in range(0, len(missing_tracks), 100):
                batch = missing_tracks[i:i+100]
                self._execute_with_retry(client.playlist_add_items, playlist_id, batch)
                added_count += len(batch)
                print(f"  Added {added_count}/{total_missing} songs...", end="\r")
            print(f"  Successfully added {added_count} songs.      ")
            
        print("\nRunning safety check for duplicates in '::seed'...")
        removed_duplicates = self.deduplicate_playlist(playlist_id)
        if removed_duplicates > 0:
            print(f"Safety check complete: cleaned up {removed_duplicates} duplicate tracks.")
        else:
            print("Safety check complete: no duplicates found.")
                
        return {
            "status": "success",
            "playlist_id": playlist_id,
            "total_saved_tracks": len(library_tracks),
            "total_playlist_tracks_collected": len(all_playlist_tracks),
            "total_unique_source_tracks": len(combined_tracks),
            "already_in_seed": len(existing_tracks),
            "added_count": added_count,
            "removed_duplicates_count": removed_duplicates
        }

if __name__ == "__main__":
    print("Testing Spotify Client Manager...")
    try:
        manager = SpotifyClientManager()
        print("Success: Client manager initialized. Credentials are set.")
        
        print("\nStarting live library synchronization to '::seed' playlist...")
        print("This will open your browser for Spotify authentication if you haven't logged in yet.")
        
        results = manager.sync_library_to_seed()
        print("\nSync completed successfully!")
        print(f"Playlist ID: {results['playlist_id']}")
        print(f"Total Liked Songs fetched: {results['total_saved_tracks']}")
        print(f"Total Playlist Songs scanned: {results['total_playlist_tracks_collected']}")
        print(f"Total Unique Source Songs: {results['total_unique_source_tracks']}")
        print(f"Songs already present in '::seed': {results['already_in_seed']}")
        print(f"New songs added to '::seed': {results['added_count']}")
        print(f"Duplicate track types cleaned up by safety net: {results['removed_duplicates_count']}")
    except ValueError as e:
        print(f"Configuration validation failed: {e}")
        print("Please check your .env configuration.")
    except Exception as e:
        print(f"An error occurred during synchronization: {e}")
