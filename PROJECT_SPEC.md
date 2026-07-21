# Spotify Vibe Curator - Project Blueprint
tired of going though your entire spotify library to create that super niche vibe playlist you listen to everyday?

## Goal
Build a Python application that helps curate hyper-specific mood/vibe playlists by evaluating tracks staged in a seed playlist (`::seed`) against a target playlist's vibe profile.

## Key Concepts
1. **Target Playlist:** The playlist we want to populate (e.g., "the wife that dies at the beginning of the movie").
2. **Anchor Songs:** 2-3 tracks that represent 100% pure match (e.g., Suki Waterhouse - "Brutally").
3. **User Vibe Description:** An optional text description provided by the user describing the narrative/emotional vibe.
4. **Seed Playlist (`::seed`):** An inbox playlist containing candidate songs to evaluate.

## Data Sources
- **Spotify API (`spotipy`):** Reads/writes playlists, track IDs, artist names, and track details.
- **Last.fm API:** Fetches track-level user tags (e.g., `#melancholic`, `#slow-piano`, `#dream-pop`).
- **LLM Evaluator:** Analyzes target description + anchor tracks + candidate track metadata to score vibe compatibility (0–100%).

## Target System Architecture
1. `spotify_client.py`: Handles Spotify OAuth 2.0 authentication and playlist operations.
2. `metadata.py`: Queries Last.fm API for track-level tags.
3. `vibe_agent.py`: Formulates LLM prompts combining Anchor Tracks + User Description + Candidate Metadata.
4. `main.py`: Interactive CLI to pick playlists, evaluate candidate tracks, and display recommendations.