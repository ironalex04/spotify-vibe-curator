import os
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

    def verify_connection(self) -> dict:
        """Verifies connectivity by fetching the authenticated user's profile.
        
        Returns:
            dict: The current user's profile information if successful.
        Raises:
            spotipy.SpotifyException: If authentication or API request fails.
        """
        client = self.get_client()
        user_info = client.current_user()
        return user_info

    def get_user_playlists(self) -> list:
        """Fetches all playlists of the authenticated user.
        
        Returns:
            list: List of playlist items.
        """
        client = self.get_client()
        playlists = []
        results = client.current_user_playlists(limit=50)
        while results:
            playlists.extend(results['items'])
            if results['next']:
                results = client.next(results)
            else:
                results = None
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
                
        new_pl = client.user_playlist_create(
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
        results = client.current_user_saved_tracks(limit=50)
        while results:
            for item in results['items']:
                track = item['track']
                if track:
                    tracks.append(track['uri'])
            if results['next']:
                results = client.next(results)
            else:
                results = None
        return tracks

    def get_playlist_tracks(self, playlist_id: str) -> list:
        """Fetches all track URIs currently in a playlist.
        
        Args:
            playlist_id: The ID of the playlist.
            
        Returns:
            list: List of track URIs.
        """
        client = self.get_client()
        tracks = []
        results = client.playlist_tracks(playlist_id, fields="items(track(uri)),next")
        while results:
            for item in results['items']:
                if item.get('track'):
                    tracks.append(item['track']['uri'])
            if results['next']:
                results = client.next(results)
            else:
                results = None
        return tracks

    def sync_library_to_seed(self) -> dict:
        """Syncs all saved tracks (Liked Songs) and tracks from all playlists 
        (except '::seed') to a playlist named '::seed'.
        
        Finds or creates the playlist. Compares existing tracks in the playlist
        with all library and playlist tracks to only add missing ones.
        
        Returns:
            dict: Sync statistics.
        """
        client = self.get_client()
        
        playlist_id = self.find_or_create_playlist(
            name="::seed",
            description="Inbox/Seed playlist for Spotify Vibe Curator. Automatically synced from Liked Songs and playlists.",
            public=False
        )
        
        existing_tracks = set(self.get_playlist_tracks(playlist_id))
        library_tracks = self.get_all_saved_tracks()
        playlists = self.get_user_playlists()
        
        all_playlist_tracks = []
        for pl in playlists:
            if pl['id'] == playlist_id or pl['name'] == "::seed":
                continue
            
            try:
                tracks = self.get_playlist_tracks(pl['id'])
                all_playlist_tracks.extend(tracks)
            except Exception as e:
                print(f"Warning: Failed to fetch tracks for playlist {pl['name']} ({pl['id']}): {e}")
        
        combined_tracks = set(library_tracks + all_playlist_tracks)
        missing_tracks = [t for t in combined_tracks if t not in existing_tracks]
        
        added_count = 0
        if missing_tracks:
            for i in range(0, len(missing_tracks), 100):
                batch = missing_tracks[i:i+100]
                client.playlist_add_items(playlist_id, batch)
                added_count += len(batch)
                
        return {
            "status": "success",
            "playlist_id": playlist_id,
            "total_saved_tracks": len(library_tracks),
            "total_playlist_tracks_collected": len(all_playlist_tracks),
            "total_unique_source_tracks": len(combined_tracks),
            "already_in_seed": len(existing_tracks),
            "added_count": added_count
        }

if __name__ == "__main__":
    print("Testing Spotify Client Manager initialization...")
    try:
        manager = SpotifyClientManager()
        print("Success: Client manager initialized. Credentials are set.")
    except ValueError as e:
        print(f"Configuration validation failed: {e}")
        print("Please check your .env configuration.")
