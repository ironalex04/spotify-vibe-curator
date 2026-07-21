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

if __name__ == "__main__":
    print("Testing Spotify Client Manager initialization...")
    try:
        manager = SpotifyClientManager()
        print("Success: Client manager initialized. Credentials are set.")
    except ValueError as e:
        print(f"Configuration validation failed: {e}")
        print("Please check your .env configuration.")
