"""
YouTube Collector — Tourism Safety & Scam Analytics Engine
IT22629180

Uses:
  - YouTube Data API v3 (free, 10k units/day) for video search
  - youtube-transcript-api v1.2+ for subtitle/transcript extraction
"""
from youtube_transcript_api import YouTubeTranscriptApi
from googleapiclient.discovery import build
from app.core.config import settings
from typing import List, Dict


class YouTubeCollector:
    def __init__(self):
        self.api_key = settings.YOUTUBE_API_KEY
        if self.api_key:
            self.youtube = build('youtube', 'v3', developerKey=self.api_key)
        else:
            self.youtube = None
            print("Warning: YouTube API key not configured.")

    def search_videos(self, query: str, max_results: int = 10) -> List[Dict]:
        if not self.youtube:
            return []
        try:
            request = self.youtube.search().list(
                q=query,
                part="snippet",
                maxResults=max_results,
                type="video"
            )
            response = request.execute()
            videos = []
            for item in response.get('items', []):
                videos.append({
                    "id": item['id']['videoId'],
                    "title": item['snippet']['title'],
                    "description": item['snippet']['description'],
                    "channel_title": item['snippet'].get('channelTitle', ''),
                    "url": f"https://www.youtube.com/watch?v={item['id']['videoId']}"
                })
            return videos
        except Exception as e:
            print(f"Error searching YouTube: {e}")
            return []

    def fetch_transcript(self, video_id: str) -> str:
        """
        Fetch transcript using youtube-transcript-api v1.2+.
        New API: YouTubeTranscriptApi.fetch(video_id)
        """
        try:
            transcript = YouTubeTranscriptApi().fetch(video_id)
            # transcript is a list of FetchedTranscriptSnippet objects
            parts = []
            for snippet in transcript:
                text = getattr(snippet, 'text', None) or str(snippet)
                if text:
                    parts.append(text)
            return " ".join(parts)
        except Exception as e:
            safe_msg = str(e).encode('ascii', errors='replace').decode('ascii')
            print(f"  Transcript unavailable for {video_id}: {safe_msg[:80]}")
            return ""

    def collect(self, query: str = "Sri Lanka tourist scams 2024", limit: int = 5) -> List[Dict]:
        NEWS_CHANNELS = [
            "Ada Derana English",
            "Newsfirst Sri Lanka",
            "Daily Mirror Online",
            "Hiru News",
            "Newswire LK"
        ]
        
        all_videos = []
        # Search each news channel specifically to restrict context
        for channel in NEWS_CHANNELS:
            channel_query = f'"{channel}" {query}'
            videos = self.search_videos(channel_query, max_results=max(1, limit // len(NEWS_CHANNELS) + 1))
            all_videos.extend(videos)
            
        # Deduplicate
        seen_ids = set()
        dedup_videos = []
        for v in all_videos:
            if v['id'] not in seen_ids:
                seen_ids.add(v['id'])
                dedup_videos.append(v)
                
        results = []
        allowed_keywords = ["derana", "newsfirst", "mirror", "hiru", "newswire"]

        for video in dedup_videos[:limit]:
            channel_title = video.get('channel_title', '').lower()
            if not any(kw in channel_title for kw in allowed_keywords):
                # Reject videos not from official news channels
                continue

            safe_title = video['title'].encode('ascii', errors='replace').decode('ascii')
            print(f"  Processing News Video: {safe_title} ({video.get('channel_title')})")
            transcript = self.fetch_transcript(video['id'])
            if transcript and len(transcript) > 50:
                results.append({
                    "source": "youtube",
                    "id": video['id'],
                    "title": video['title'],
                    "content": transcript,
                    "url": video['url']
                })
            elif not transcript:
                # Still save the title + description as content (valuable data)
                desc = video.get('description', '')
                content = f"{video['title']}. {desc}".strip()
                if len(content) > 30:
                    results.append({
                        "source": "youtube",
                        "id": video['id'],
                        "title": video['title'],
                        "content": content,
                        "url": video['url']
                    })

        return results
