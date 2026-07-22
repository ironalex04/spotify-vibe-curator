import os
import unittest
from unittest.mock import MagicMock, patch

from spotify_client import SpotifyClientManager
from metadata import LastFMClient
from vibe_agent import VibeAgent
import main

class TestSpotifyClientManager(unittest.TestCase):
    
    def setUp(self):
        # Setup dummy credentials for tests
        self.dummy_credentials = {
            "client_id": "dummy_client_id",
            "client_secret": "dummy_client_secret",
            "redirect_uri": "http://127.0.0.1:8888/callback"
        }

    def test_missing_credentials_raises_value_error(self):
        # Force missing credentials by clearing env and constructor params
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                SpotifyClientManager()

    def test_explicit_credentials_bypass_env(self):
        manager = SpotifyClientManager(**self.dummy_credentials)
        self.assertEqual(manager.client_id, "dummy_client_id")
        self.assertEqual(manager.client_secret, "dummy_client_secret")
        self.assertEqual(manager.redirect_uri, "http://127.0.0.1:8888/callback")

    @patch("spotify_client.spotipy.Spotify")
    def test_sync_library_to_seed_logic(self, mock_spotify_class):
        # 1. Create a mocked Spotify client
        mock_client = MagicMock()
        mock_spotify_class.return_value = mock_client
        
        # 2. Mock client.current_user() for verify_connection
        mock_client.current_user.return_value = {"id": "test_user_123"}
        
        # 3. Mock playlists list
        mock_client.current_user_playlists.return_value = {
            "items": [
                {"name": "Some Playlist", "id": "pl_1"},
                {"name": "::seed", "id": "seed_pl_id"}
            ],
            "next": None
        }
        
        # 4. Mock playlist tracks using side_effect to return different values for ::seed vs pl_1
        def mock_playlist_tracks(playlist_id, *args, **kwargs):
            if playlist_id == "seed_pl_id":
                return {
                    "items": [
                        {"track": {"uri": "spotify:track:existing1"}},
                        {"track": {"uri": "spotify:track:existing2"}}
                    ],
                    "next": None
                }
            elif playlist_id == "pl_1":
                return {
                    "items": [
                        {"track": {"uri": "spotify:track:playlist_track_1"}},
                        {"track": {"uri": "spotify:track:existing1"}}
                    ],
                    "next": None
                }
            return {"items": [], "next": None}
            
        mock_client.playlist_tracks.side_effect = mock_playlist_tracks
        
        # 5. Mock saved tracks in library (has 4 tracks, 2 are already in ::seed, 2 are new)
        mock_client.current_user_saved_tracks.return_value = {
            "items": [
                {"track": {"uri": "spotify:track:existing1"}},
                {"track": {"uri": "spotify:track:existing2"}},
                {"track": {"uri": "spotify:track:new_track_1"}},
                {"track": {"uri": "spotify:track:new_track_2"}}
            ],
            "next": None
        }
        
        # 6. Initialize manager and execute sync
        manager = SpotifyClientManager(**self.dummy_credentials)
        sync_result = manager.sync_library_to_seed()
        
        # 7. Assertions
        # Check that it found the existing playlist ID
        self.assertEqual(sync_result["playlist_id"], "seed_pl_id")
        # Check statistics
        self.assertEqual(sync_result["total_saved_tracks"], 4)
        self.assertEqual(sync_result["total_playlist_tracks_collected"], 2) # from pl_1
        # Combined unique tracks = {existing1, existing2, new_track_1, new_track_2, playlist_track_1} = 5 tracks
        self.assertEqual(sync_result["total_unique_source_tracks"], 5)
        # Check that 3 tracks were added: new_track_1, new_track_2, playlist_track_1
        self.assertEqual(sync_result["added_count"], 3)
        
        # Verify playlist_add_items call. Since order inside set/list diff can vary, let's sort the arguments.
        mock_client.playlist_add_items.assert_called_once()
        call_args = mock_client.playlist_add_items.call_args[0]
        self.assertEqual(call_args[0], "seed_pl_id")
        self.assertEqual(sorted(call_args[1]), sorted([
            "spotify:track:new_track_1", 
            "spotify:track:new_track_2", 
            "spotify:track:playlist_track_1"
        ]))

    @patch("spotify_client.spotipy.Spotify")
    def test_deduplicate_playlist(self, mock_spotify_class):
        mock_client = MagicMock()
        mock_spotify_class.return_value = mock_client
        
        # Mock playlist_tracks to return duplicate tracks and verify track/item fallbacks
        mock_client.playlist_tracks.return_value = {
            "items": [
                {"track": {"uri": "spotify:track:1"}},
                {"item": {"uri": "spotify:track:2"}},
                {"track": {"uri": "spotify:track:1"}},
                {"item": {"uri": "spotify:track:3"}},
                {"track": {"uri": "spotify:track:2"}}
            ],
            "next": None
        }
        
        manager = SpotifyClientManager(**self.dummy_credentials)
        duplicates_removed = manager.deduplicate_playlist("seed_pl_id")
        
        self.assertEqual(duplicates_removed, 2)
        mock_client.playlist_remove_all_occurrences_of_items.assert_called_once()
        mock_client.playlist_add_items.assert_called_once()
        
        remove_args = mock_client.playlist_remove_all_occurrences_of_items.call_args[0]
        add_args = mock_client.playlist_add_items.call_args[0]
        
        self.assertEqual(remove_args[0], "seed_pl_id")
        self.assertEqual(sorted(remove_args[1]), ["spotify:track:1", "spotify:track:2"])
        self.assertEqual(add_args[0], "seed_pl_id")
        self.assertEqual(sorted(add_args[1]), ["spotify:track:1", "spotify:track:2"])

    @patch("spotify_client.spotipy.Spotify")
    @patch("spotify_client.time.sleep")
    def test_execute_with_retry_on_rate_limit(self, mock_sleep, mock_spotify_class):
        from spotipy.exceptions import SpotifyException
        
        mock_func = MagicMock()
        rate_limit_exc = SpotifyException(
            http_status=429,
            code=-1,
            msg="Rate limit reached",
            headers={"Retry-After": "3"}
        )
        mock_func.side_effect = [rate_limit_exc, "success_result"]
        
        manager = SpotifyClientManager(**self.dummy_credentials)
        result = manager._execute_with_retry(mock_func, "arg1", kwarg1="val1")
        
        mock_sleep.assert_called_once_with(3)
        self.assertEqual(result, "success_result")
        self.assertEqual(mock_func.call_count, 2)
        mock_func.assert_called_with("arg1", kwarg1="val1")

class TestLastFMClient(unittest.TestCase):
    
    def test_missing_api_key_raises_value_error(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                LastFMClient()

    @patch("metadata.requests.get")
    def test_get_track_tags_success(self, mock_get):
        # 1. Setup mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "toptags": {
                "tag": [
                    {"name": "Dream Pop", "count": "100"},
                    {"name": "indie", "count": 80},
                    {"name": "female vocalists", "count": "invalid_count"}
                ]
            }
        }
        mock_get.return_value = mock_response
        
        # 2. Initialize client and query tags
        client = LastFMClient(api_key="dummy_lastfm_key")
        tags = client.get_track_tags("Suki Waterhouse", "Brutally")
        
        # 3. Assertions
        # Validate that we get exactly 3 tags
        self.assertEqual(len(tags), 3)
        # Validate lowercasing and count conversions
        self.assertEqual(tags[0], {"name": "dream pop", "count": 100})
        self.assertEqual(tags[1], {"name": "indie", "count": 80})
        # Invalid count should fallback to 0
        self.assertEqual(tags[2], {"name": "female vocalists", "count": 0})
        
        # Check correct API call structure
        mock_get.assert_called_once()
        called_args, called_kwargs = mock_get.call_args
        self.assertEqual(called_kwargs["params"]["method"], "track.getTopTags")
        self.assertEqual(called_kwargs["params"]["artist"], "Suki Waterhouse")
        self.assertEqual(called_kwargs["params"]["track"], "Brutally")

    @patch("metadata.requests.get")
    def test_get_track_tags_not_found(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "error": 6,
            "message": "Track not found"
        }
        mock_get.return_value = mock_response
        
        client = LastFMClient(api_key="dummy_lastfm_key")
        tags = client.get_track_tags("NonExistentArtist", "NonExistentTrack")
        
        self.assertEqual(tags, [])

class TestVibeAgent(unittest.TestCase):
    
    def test_missing_api_key_raises_value_error(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                VibeAgent()

    @patch("vibe_agent.requests.post")
    def test_evaluate_track_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": '{"score": 85, "reasoning": "Fits the melancholic profile of the anchors."}'
                            }
                        ]
                    }
                }
            ]
        }
        mock_post.return_value = mock_response
        
        agent = VibeAgent(api_key="dummy_gemini_key")
        result = agent.evaluate_track(
            vibe_description="melancholic bedroom pop",
            anchor_tracks=[{"title": "Brutally", "artist": "Suki Waterhouse", "tags": ["dream pop", "melancholy"]}],
            candidate_track={"title": "Some Song", "artist": "Some Artist", "tags": ["indie pop", "melancholy"]}
        )
        
        self.assertEqual(result["score"], 85)
        self.assertEqual(result["reasoning"], "Fits the melancholic profile of the anchors.")
        
        mock_post.assert_called_once()
        called_args, called_kwargs = mock_post.call_args
        self.assertEqual(called_kwargs["params"]["key"], "dummy_gemini_key")
        payload = called_kwargs["json"]
        self.assertEqual(payload["generationConfig"]["temperature"], 0.2)
        self.assertEqual(payload["generationConfig"]["responseMimeType"], "application/json")

class TestMainCLI(unittest.TestCase):
    
    @patch("main.check_env_vars")
    @patch("main.SpotifyClientManager")
    @patch("main.LastFMClient")
    @patch("main.VibeAgent")
    @patch("main.input")
    @patch("main.sys.exit")
    def test_run_cli_success(self, mock_exit, mock_input, mock_vibe_agent_class, mock_lastfm_client_class, mock_spotify_manager_class, mock_check_env):
        mock_check_env.return_value = True
        
        mock_spotify = MagicMock()
        mock_spotify.verify_connection.return_value = {"display_name": "Test User", "id": "user123"}
        mock_spotify.get_user_playlists.return_value = [{"name": "::seed", "id": "seed_id"}]
        mock_spotify.get_playlist_tracks_detailed.return_value = [
            {"uri": "spotify:track:candidate1", "title": "Candidate Song", "artist": "Candidate Artist"}
        ]
        mock_spotify.find_or_create_playlist.return_value = "new_pl_id"
        mock_spotify_manager_class.return_value = mock_spotify
        
        mock_lastfm = MagicMock()
        mock_lastfm.get_track_tags.return_value = [{"name": "melancholy", "count": 100}]
        mock_lastfm_client_class.return_value = mock_lastfm
        
        mock_vibe = MagicMock()
        mock_vibe.evaluate_track.return_value = {"score": 90, "reasoning": "Perfect fit."}
        mock_vibe_agent_class.return_value = mock_vibe
        
        mock_input.side_effect = [
            "n",                     # Do you want to sync your Liked Songs?
            "dreamy bedroom pop",    # Enter description of the vibe
            "Anchor 1",              # Anchor 1 title
            "Artist 1",              # Anchor 1 artist
            "Anchor 2",              # Anchor 2 title
            "Artist 2",              # Anchor 2 artist
            "y",                     # Skip Anchor Song 3?
            "Dreamy Pop Curated",    # Name of new playlist
            "80"                     # Score threshold
        ]
        
        main.run_cli()
        
        mock_spotify.verify_connection.assert_called_once()
        mock_spotify.get_playlist_tracks_detailed.assert_called_once_with("seed_id", "::seed")
        mock_vibe.evaluate_track.assert_called_once()
        mock_spotify.find_or_create_playlist.assert_called_once_with(
            name="Dreamy Pop Curated",
            description="Curated mood playlist: dreamy bedroom pop. Generated by Spotify Vibe Curator.",
            public=False
        )
        mock_spotify.deduplicate_playlist.assert_called_once_with("new_pl_id")
        mock_exit.assert_not_called()

if __name__ == "__main__":
    unittest.main()
