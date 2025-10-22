import os
import requests
from dotenv import load_dotenv
import re
import json
from typing import Optional, List, Dict

load_dotenv()


class FacebookCommentScraper:
    """
    Simple scraper for Facebook post comments
    Outputs: username, timestamp, comment text to JSON
    """

    def __init__(self):
        self.access_token = os.getenv('FACEBOOK_ACCESS_TOKEN')
        self.group_id = os.getenv('HAWAII_TRACKER_GROUP_ID')  # Get from .env
        self.base_url = 'https://graph.facebook.com/v21.0'

        if not self.access_token:
            raise ValueError("FACEBOOK_ACCESS_TOKEN not found in .env file")

        if not self.group_id:
            raise ValueError("HAWAII_TRACKER_GROUP_ID not found in .env file")

        print(f"Using Group ID from .env: {self.group_id}")

    def extract_post_id_from_url(self, url: str) -> Optional[str]:
        """
        Extract just the post ID from the URL
        We'll combine it with the group ID from .env
        """
        print(f"\nExtracting Post ID from URL...")
        print(f"Original URL: {url}")

        # Clean the URL
        clean_url = url.split('?')[0].split('#')[0]
        print(f"Cleaned URL: {clean_url}")

        # Extract post ID (from permalink or posts)
        post_match = re.search(r'/(?:permalink|posts)/(\d+)', clean_url)
        if post_match:
            post_id = post_match.group(1)
            print(f"✓ Post ID: {post_id}")
            return post_id

        # Fallback: try to find any long number (15+ digits)
        numbers = re.findall(r'\d{15,}', clean_url)
        if numbers:
            post_id = numbers[-1]  # Take the last one (usually the post ID)
            print(f"✓ Post ID (extracted): {post_id}")
            return post_id

        print("✗ Could not extract Post ID from URL")
        return None

    def get_all_comments(self, post_id: str) -> List[Dict]:
        """
        Fetch all comments from a post
        Returns: List of dicts with {username, timestamp, comment}

        Note: post_id should be in format "GROUP_ID_POST_ID"
        """
        print(f"\nFetching comments for post {post_id}...")

        all_comments = []
        url = f'{self.base_url}/{post_id}/comments'
        params = {
            'fields': 'from,message,created_time',
            'limit': 100,
            'access_token': self.access_token
        }

        page_count = 0

        try:
            while True:
                page_count += 1
                response = requests.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                comments = data.get('data', [])

                # Extract only the needed fields
                for comment in comments:
                    # Get username - handle "Unknown" case
                    from_data = comment.get('from', {})
                    username = from_data.get('name', 'Unknown User')

                    all_comments.append({
                        'username': username,
                        'timestamp': comment.get('created_time', ''),
                        'comment': comment.get('message', '')
                    })

                print(f"  Page {page_count}: +{len(comments)} comments (Total: {len(all_comments)})")

                # Check for next page
                paging = data.get('paging', {})
                next_url = paging.get('next')

                if not next_url:
                    break

                url = next_url
                params = {}

            print(f"✓ Total comments fetched: {len(all_comments)}")
            return all_comments

        except requests.exceptions.HTTPError as e:
            print(f"✗ Failed to fetch comments: {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    error_msg = error_data.get('error', {}).get('message', 'Unknown')
                    print(f"  Error: {error_msg}")

                    if 'permission' in error_msg.lower():
                        print("\n  Permission issue detected!")
                        print("  Make sure your access token has:")
                        print("    • groups_access_member_info")
                        print("    • publish_to_groups")
                except:
                    pass
            return all_comments

    def export_to_json(self, comments: List[Dict], filename: str = 'comments.json') -> bool:
        """Export comments to JSON file"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(comments, f, indent=2, ensure_ascii=False)

            file_size_kb = os.path.getsize(filename) / 1024
            print(f"\n✓ Exported {len(comments)} comments to {filename}")
            print(f"  File size: {file_size_kb:.2f} KB")
            return True

        except Exception as e:
            print(f"\n✗ Export failed: {e}")
            return False

    def scrape_post(self, post_url: str, output_file: str = 'comments.json') -> List[Dict]:
        """
        Main function: URL → Comments → JSON
        Uses the group ID from .env file
        """
        print("=" * 80)
        print("FACEBOOK COMMENT SCRAPER")
        print("=" * 80)

        # Extract just the post ID from URL
        post_id = self.extract_post_id_from_url(post_url)
        if not post_id:
            print("\n✗ Failed: Could not extract post ID from URL")
            return None

        # Construct full post ID using .env group ID: GROUP_ID_POST_ID
        full_post_id = f"{self.group_id}_{post_id}"
        print(f"\nConstructing full post ID:")
        print(f"  Group ID (from .env): {self.group_id}")
        print(f"  Post ID (from URL): {post_id}")
        print(f"  Full Post ID: {full_post_id}")

        # Fetch comments
        comments = self.get_all_comments(full_post_id)
        if not comments:
            print("\n⚠️  No comments found")
            return []

        # Export to JSON
        success = self.export_to_json(comments, output_file)

        if success:
            print("\n" + "=" * 80)
            print("✓ SUCCESS")
            print("=" * 80)
            print(f"Comments saved to: {output_file}")
            print(f"Total comments: {len(comments)}")

        return comments


def main():
    """Interactive CLI"""
    print("\n" + "=" * 80)
    print("FACEBOOK COMMENT SCRAPER")
    print("=" * 80)

    try:
        scraper = FacebookCommentScraper()

        print("\nPaste the Facebook post permalink URL")
        print("(The group ID will be taken from your .env file)")
        print("\nSupported URL formats:")
        print("  • facebook.com/groups/hawaiitracker/permalink/789012/")
        print("  • facebook.com/groups/123456/permalink/789012/")

        post_url = input("\nPost URL: ").strip()

        if not post_url:
            print("No URL provided. Exiting.")
            return

        # Ask for output filename
        filename = input("\nOutput filename (press Enter for 'comments.json'): ").strip()
        if not filename:
            filename = 'comments.json'

        # Ensure .json extension
        if not filename.endswith('.json'):
            filename += '.json'

        # Scrape and export
        comments = scraper.scrape_post(post_url, filename)

        if comments:
            print(f"\n✓ Done! Check {filename} for the results.")
        else:
            print("\n✗ Failed to scrape comments.")

    except ValueError as e:
        print(f"\n✗ Configuration Error: {e}")
        print("\nMake sure you have a .env file with:")
        print("  FACEBOOK_ACCESS_TOKEN=your_token_here")
        print("  HAWAII_TRACKER_GROUP_ID=your_group_id_here")
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")


if __name__ == '__main__':
    main()