import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root to path (just in case)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from spotify_client import SpotifyClientManager
from metadata import LastFMClient
from vibe_agent import VibeAgent

def check_env_vars():
    """Checks that all required environment variables are set."""
    missing = []
    if not os.getenv("SPOTIPY_CLIENT_ID"):
        missing.append("SPOTIPY_CLIENT_ID")
    if not os.getenv("SPOTIPY_CLIENT_SECRET"):
        missing.append("SPOTIPY_CLIENT_SECRET")
    if not os.getenv("SPOTIPY_REDIRECT_URI"):
        missing.append("SPOTIPY_REDIRECT_URI")
    if not os.getenv("LASTFM_API_KEY"):
        missing.append("LASTFM_API_KEY")
    if not os.getenv("GEMINI_API_KEY"):
        missing.append("GEMINI_API_KEY")
        
    if missing:
        print("\n[Configuration Error] Missing required keys in your environment or .env file:")
        for var in missing:
            print(f"  - {var}")
        print("\nPlease create a '.env' file from '.env.example' and fill in all variables.")
        return False
    return True

def get_input(prompt: str, default: str = "") -> str:
    """Helper to get user input with a default option."""
    if default:
        res = input(f"{prompt} [{default}]: ").strip()
        return res if res else default
    return input(prompt).strip()

def run_cli():
    print("=" * 60)
    print("              SPOTIFY VIBE CURATOR - CLI               ")
    print("=" * 60)
    
    if not check_env_vars():
        sys.exit(1)
        
    # Initialize clients
    print("\nInitializing API clients...")
    try:
        spotify_manager = SpotifyClientManager()
        # Test connection immediately
        user_info = spotify_manager.verify_connection()
        print(f"  - Spotify Client: Connected as user '{user_info.get('display_name', user_info.get('id'))}'")
    except Exception as e:
        print(f"\n[Error] Failed to connect to Spotify API: {e}")
        print("Please check your Spotify credentials and internet connection.")
        sys.exit(1)
        
    try:
        lastfm_client = LastFMClient()
        print("  - Last.fm Client: Initialized")
    except Exception as e:
        print(f"\n[Error] Failed to initialize Last.fm client: {e}")
        sys.exit(1)
        
    try:
        vibe_agent = VibeAgent()
        print("  - Vibe Agent (Gemini): Initialized")
    except Exception as e:
        print(f"\n[Error] Failed to initialize Gemini Vibe Agent: {e}")
        sys.exit(1)
        
    # Step 1: Optional Library Sync
    print("\n" + "-" * 40)
    print("STEP 1: Library Synchronization")
    print("-" * 40)
    sync_choice = get_input("Do you want to sync your Liked Songs and playlists to the '::seed' playlist? (y/n)", "n").lower()
    if sync_choice in ['y', 'yes']:
        print("\nStarting library sync to '::seed' playlist...")
        try:
            sync_results = spotify_manager.sync_library_to_seed()
            print("\nSync completed successfully!")
            print(f"  - Total Liked Songs: {sync_results['total_saved_tracks']}")
            print(f"  - Total Playlist Songs scanned: {sync_results['total_playlist_tracks_collected']}")
            print(f"  - Unique Source Songs: {sync_results['total_unique_source_tracks']}")
            print(f"  - New songs added to '::seed': {sync_results['added_count']}")
        except Exception as e:
            print(f"\n[Sync Warning] Sync encountered an issue: {e}")
            print("We will attempt to proceed using the existing '::seed' playlist.")

    # Step 2: Define Vibe Profile
    print("\n" + "-" * 40)
    print("STEP 2: Define Target Vibe Profile")
    print("-" * 40)
    vibe_desc = get_input("Enter a description of the vibe (narrative, mood, energy):")
    if not vibe_desc:
        print("Vibe description is required.")
        sys.exit(1)
        
    print("\nNow, enter 2-3 Anchor Songs representing 100% vibe match.")
    anchor_tracks = []
    for i in range(1, 4):
        # We need at least 2 anchor tracks. If we have 2, we can skip the 3rd.
        if i == 3:
            skip = get_input(f"Do you want to skip Anchor Song 3? (y/n)", "y").lower()
            if skip in ['y', 'yes']:
                break
                
        print(f"\nAnchor Song #{i}:")
        title = get_input("  Track Title:")
        while not title:
            print("  Title cannot be empty.")
            title = get_input("  Track Title:")
            
        artist = get_input("  Artist Name:")
        while not artist:
            print("  Artist cannot be empty.")
            artist = get_input("  Artist Name:")
            
        print(f"  Fetching tags for '{title}' by {artist}...")
        tags_data = lastfm_client.get_track_tags(artist, title)
        tags = [t['name'] for t in tags_data]
        print(f"  Tags found: {', '.join(tags) if tags else 'None'}")
        
        anchor_tracks.append({
            "title": title,
            "artist": artist,
            "tags": tags
        })

    # Step 3: Playlist Settings
    print("\n" + "-" * 40)
    print("STEP 3: Playlist Settings")
    print("-" * 40)
    target_playlist_name = get_input("Enter the name of the new Vibe playlist:", "Vibe Curator Playlist")
    threshold_str = get_input("Enter minimum compatibility score threshold (0-100):", "75")
    try:
        threshold = int(threshold_str)
    except ValueError:
        threshold = 75
        print("Invalid threshold. Defaulting to 75.")

    # Step 4: Retrieve and Evaluate Candidate Tracks
    print("\n" + "-" * 40)
    print("STEP 4: Candidate Tracks Evaluation")
    print("-" * 40)
    
    # Check if '::seed' exists and get its tracks
    playlists = spotify_manager.get_user_playlists()
    seed_playlist = None
    for pl in playlists:
        if pl['name'] == "::seed":
            seed_playlist = pl
            break
            
    if not seed_playlist:
        print("[Error] '::seed' playlist does not exist in your account.")
        print("Please run this script again and select 'y' to synchronize your library first.")
        sys.exit(1)
        
    print(f"Fetching detailed track list from '::seed' playlist...")
    candidates = spotify_manager.get_playlist_tracks_detailed(seed_playlist['id'], "::seed")
    
    if not candidates:
        print("\n'::seed' playlist is empty. Please run sync or add songs to '::seed' manually.")
        sys.exit(1)
        
    print(f"Found {len(candidates)} candidate tracks to evaluate.")
    print(f"Starting evaluations (filtering for score >= {threshold}%)...")
    
    matching_uris = []
    
    for idx, cand in enumerate(candidates, 1):
        print(f"\n[{idx}/{len(candidates)}] Evaluating '{cand['title']}' by {cand['artist']}...")
        
        # 1. Fetch tags for candidate
        tags_data = lastfm_client.get_track_tags(cand['artist'], cand['title'])
        cand['tags'] = [t['name'] for t in tags_data]
        
        # 2. Score via Gemini
        evaluation = vibe_agent.evaluate_track(vibe_desc, anchor_tracks, cand)
        score = evaluation.get("score", 0)
        reasoning = evaluation.get("reasoning", "No explanation provided.")
        
        print(f"  Score: {score}%")
        print(f"  Reason: {reasoning}")
        
        if score >= threshold:
            matching_uris.append(cand['uri'])
            print("  -> MATCH: Saved for addition!")
            
    # Step 5: Save Results
    print("\n" + "-" * 40)
    print("STEP 5: Save Playlist")
    print("-" * 40)
    
    if not matching_uris:
        print("No tracks met the similarity threshold. No playlist created.")
        print("Try lowering the threshold or refining your vibe description/anchors.")
        sys.exit(0)
        
    print(f"Found {len(matching_uris)} matching tracks.")
    print(f"Finding or creating target playlist '{target_playlist_name}'...")
    
    try:
        target_id = spotify_manager.find_or_create_playlist(
            name=target_playlist_name,
            description=f"Curated mood playlist: {vibe_desc}. Generated by Spotify Vibe Curator.",
            public=False
        )
        
        print(f"Adding matching songs to '{target_playlist_name}'...")
        # Add in batches of 100 (Spotify API limit)
        spotify_client = spotify_manager.get_client()
        for i in range(0, len(matching_uris), 100):
            batch = matching_uris[i:i+100]
            spotify_manager._execute_with_retry(spotify_client.playlist_add_items, target_id, batch)
            
        print("\nDeduplicating target playlist...")
        spotify_manager.deduplicate_playlist(target_id)
        
        print(f"\nSUCCESS! Playlist '{target_playlist_name}' is ready in your Spotify library.")
        print("Thank you for using Spotify Vibe Curator!")
        
    except Exception as e:
        print(f"\n[Error] Failed to create or populate target playlist: {e}")
        sys.exit(1)

if __name__ == "__main__":
    try:
        run_cli()
    except KeyboardInterrupt:
        print("\n\nExecution cancelled by user. Exiting.")
        sys.exit(0)
