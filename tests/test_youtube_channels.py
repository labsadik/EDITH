import unittest
from unittest.mock import patch

from actions import youtube_video as youtube_module


class YouTubeChannelSearchTests(unittest.TestCase):
    def test_channel_search_opens_channel_filtered_results_without_video_scrape(self):
        with (
            patch.object(youtube_module, "_open_url") as open_url,
            patch.object(youtube_module, "_scrape_first_video_url") as scrape_video,
        ):
            result = youtube_module.youtube_video(
                {"action": "channel", "query": "CarryMinati"}
            )
        open_url.assert_called_once()
        url = open_url.call_args.args[0]
        self.assertIn("search_query=CarryMinati", url)
        self.assertIn("sp=EgIQAg%3D%3D", url)
        self.assertIn("channel-only", result)
        self.assertIn("No video was auto-played", result)
        scrape_video.assert_not_called()

    def test_empty_channel_search_does_not_open_browser(self):
        with patch.object(youtube_module, "_open_url") as open_url:
            result = youtube_module.youtube_video({"action": "channel", "query": ""})
        self.assertIn("channel name", result)
        open_url.assert_not_called()


if __name__ == "__main__":
    unittest.main()
