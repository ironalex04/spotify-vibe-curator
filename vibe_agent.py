import os
import json
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

class VibeAgent:
    """Uses Gemini API via direct REST requests to evaluate track vibe compatibility based on anchor songs and descriptions."""

    def __init__(self, api_key: str = None):
        """Initializes the VibeAgent with a Gemini API key.
        
        Args:
            api_key: The Gemini API key. If not provided, it will fall back to GEMINI_API_KEY environment variable.
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self._validate_credentials()

    def _validate_credentials(self):
        """Validates that the Gemini API key is set."""
        if not self.api_key:
            raise ValueError(
                "Missing Gemini API credentials: GEMINI_API_KEY. "
                "Please configure this in your environment or a .env file."
            )

    def evaluate_track(self, vibe_description: str, anchor_tracks: list, candidate_track: dict) -> dict:
        """Evaluates a single candidate track against the target vibe profile.
        
        Args:
            vibe_description: A text description of the target playlist vibe.
            anchor_tracks: A list of dicts representing anchor tracks, e.g.:
                           [{"title": "...", "artist": "...", "tags": ["tag1", "tag2"]}]
            candidate_track: A dict representing the track to evaluate:
                             {"title": "...", "artist": "...", "tags": ["tag1", "tag2"]}
                             
        Returns:
            dict: A dictionary containing {"score": int, "reasoning": str}.
                  Returns a default fallback evaluation if API call fails.
        """
        # Format anchor tracks details
        anchor_details_list = []
        for i, track in enumerate(anchor_tracks, 1):
            tags_str = ", ".join(track.get("tags", [])) or "No tags available"
            anchor_details_list.append(
                f"{i}. '{track.get('title')}' by {track.get('artist')} (Tags: {tags_str})"
            )
        anchor_tracks_str = "\n".join(anchor_details_list)

        # Format candidate details
        candidate_tags_str = ", ".join(candidate_track.get("tags", [])) or "No tags available"

        # Construct prompt
        prompt = f"""You are the Spotify Vibe Curator, an expert AI music assistant.
Your task is to evaluate how well a Candidate Track fits a target "Vibe Profile" defined by a Vibe Description and a set of 2-3 Anchor Tracks.

Target Vibe Description:
"{vibe_description}"

Anchor Tracks (Represent a 100% vibe match):
{anchor_tracks_str}

Candidate Track to Evaluate:
- Title: "{candidate_track.get('title')}"
- Artist: {candidate_track.get('artist')}
- Last.fm Tags: {candidate_tags_str}

Compare the Candidate Track with the Vibe Profile. Evaluate the similarity in genre, mood, tempo, emotional narrative, and acoustic style as indicated by the tags and description.
Provide:
1. A compatibility score (integer from 0 to 100) where 100 means a perfect fit and 0 means completely out of place.
2. A concise 1-2 sentence explanation of your reasoning.
"""

        # Construct request payload for Gemini API
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "OBJECT",
                    "properties": {
                        "score": {
                            "type": "INTEGER",
                            "description": "Compatibility score from 0 to 100 on how well the candidate track fits the target vibe profile."
                        },
                        "reasoning": {
                            "type": "STRING",
                            "description": "A concise 1-2 sentence explanation of why the track received this score, referencing specific tags and description details."
                        }
                    },
                    "required": ["score", "reasoning"]
                },
                "temperature": 0.2
            }
        }

        params = {"key": self.api_key}
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.post(GEMINI_API_URL, params=params, json=payload, headers=headers, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            
            # Extract JSON output text from candidates
            candidates = data.get("candidates", [])
            if not candidates:
                raise ValueError("No candidates returned from Gemini API.")
                
            text_output = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            if not text_output:
                raise ValueError("Empty text content in Gemini response.")
                
            # Parse the structured JSON output
            result = json.loads(text_output.strip())
            return result
            
        except Exception as e:
            # Print error and return a safe fallback score (0) to allow execution to proceed
            print(f"Error calling Gemini API for track '{candidate_track.get('title')}': {e}")
            return {
                "score": 0,
                "reasoning": f"Failed to evaluate track due to an API error: {e}"
            }

if __name__ == "__main__":
    print("Testing Vibe Agent initialization...")
    try:
        agent = VibeAgent()
        print("Success: Vibe Agent client initialized. API key is set.")
    except ValueError as e:
        print(f"Configuration validation failed: {e}")
        print("Please check your .env configuration.")
