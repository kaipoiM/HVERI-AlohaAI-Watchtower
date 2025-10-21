import os
import requests
from dotenv import load_dotenv
from datetime import datetime
import json
import time

# Load environment variables
load_dotenv()


class FacebookGraphAPI:
    def __init__(self):
        self.access_token = os.getenv('FACEBOOK_ACCESS_TOKEN')
        self.group_id = os.getenv('HAWAII_TRACKER_GROUP_ID')
        self.user_id = os.getenv('HAWAII_TRACKER_USER_ID')
        self.base_url = 'https://graph.facebook.com/v21.0'

        # Validate credentials
        if not self.access_token:
            raise ValueError("FACEBOOK_ACCESS_TOKEN not found in .env file")
        if not self.group_id:
            raise ValueError("HAWAII_TRACKER_GROUP_ID not found in .env file")

    def test_basic_access(self):
        """Test basic API access - Step 6.1 from guide"""
        print("\n" + "=" * 80)
        print("TEST 1: Basic API Access")
        print("=" * 80)

        url = f'{self.base_url}/{self.user_id}'
        params = {
            'fields': 'id,name,email',
            'access_token': self.access_token
        }

        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            print("✓ Basic API access successful!")
            print(f"  User ID: {data.get('id')}")
            print(f"  Name: {data.get('name')}")
            print(f"  Email: {data.get('email', 'Not provided')}")
            return True
        except requests.exceptions.RequestException as e:
            print(f"✗ Basic API access failed: {e}")
            if hasattr(e.response, 'json'):
                print(f"  Error details: {e.response.json()}")
            return False

    def test_group_access(self):
        """Test group access - Step 6.2 from guide"""
        print("\n" + "=" * 80)
        print("TEST 2: Group Access")
        print("=" * 80)

        url = f'{self.base_url}/{self.group_id}'
        params = {
            'fields': 'id,name,description,member_count',
            'access_token': self.access_token
        }

        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            print("✓ Group access successful!")
            print(f"  Group ID: {data.get('id')}")
            print(f"  Name: {data.get('name')}")
            print(f"  Members: {data.get('member_count', 'Unknown')}")
            print(f"  Description: {data.get('description', 'None')[:100]}...")
            return True
        except requests.exceptions.RequestException as e:
            print(f"✗ Group access failed: {e}")
            if hasattr(e.response, 'json'):
                print(f"  Error details: {e.response.json()}")
            return False

    def get_group_posts(self, limit=10):
        """Fetch recent posts from group - Step 7.1 from guide"""
        print("\n" + "=" * 80)
        print(f"TEST 3: Fetching {limit} Recent Posts")
        print("=" * 80)

        # Clean the group ID (remove any accidental characters)
        clean_group_id = str(self.group_id).split('#')[0].split('?')[0].strip()

        print(f"Group ID from .env: '{self.group_id}'")
        print(f"Cleaned Group ID: '{clean_group_id}'")

        url = f'{self.base_url}/{clean_group_id}/feed'
        params = {
            'fields': 'id,message,created_time,from,comments.limit(5){id,from,message,created_time}',
            'limit': limit,
            'access_token': self.access_token
        }

        print(f"Requesting URL: {url}")

        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            posts = data.get('data', [])
            print(f"✓ Successfully fetched {len(posts)} posts")

            for i, post in enumerate(posts, 1):
                print(f"\nPost {i}:")
                print(f"  ID: {post.get('id')}")
                print(f"  From: {post.get('from', {}).get('name', 'Unknown')}")
                print(f"  Time: {post.get('created_time')}")
                message = post.get('message', 'No message')
                print(f"  Message: {message[:100]}{'...' if len(message) > 100 else ''}")

                comments = post.get('comments', {}).get('data', [])
                print(f"  Comments preview: {len(comments)} shown")

            return data
        except requests.exceptions.RequestException as e:
            print(f"✗ Failed to fetch posts: {e}")
            if hasattr(e.response, 'json'):
                print(f"  Error details: {e.response.json()}")
            return None

    def get_post_comments(self, post_id, limit=100):
        """Fetch all comments for a specific post - Step 7.2 from guide"""
        print(f"\nFetching comments for post: {post_id}")

        url = f'{self.base_url}/{post_id}/comments'
        params = {
            'fields': 'id,from,message,created_time,permalink_url',
            'limit': limit,
            'access_token': self.access_token
        }

        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            comments = data.get('data', [])
            print(f"✓ Fetched {len(comments)} comments")

            return data
        except requests.exceptions.RequestException as e:
            print(f"✗ Failed to fetch comments: {e}")
            if hasattr(e.response, 'json'):
                print(f"  Error details: {e.response.json()}")
            return None

    def get_new_comments_since(self, post_id, since_timestamp):
        """Get only new comments since last check (for 30-min cycles)"""
        url = f'{self.base_url}/{post_id}/comments'
        params = {
            'fields': 'id,from,message,created_time,permalink_url',
            'since': since_timestamp,  # Unix timestamp
            'limit': 500,
            'access_token': self.access_token
        }

        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching new comments: {e}")
            return None

    def test_full_workflow(self):
        """Test complete workflow for AlohaAI Watchtower"""
        print("\n" + "=" * 80)
        print("TEST 4: Full Workflow Simulation")
        print("=" * 80)

        # Get recent posts
        posts_data = self.get_group_posts(limit=3)
        if not posts_data:
            print("Cannot proceed with workflow test - posts fetch failed")
            return

        posts = posts_data.get('data', [])
        if not posts:
            print("No posts found in group")
            return

        # Test comment fetching on first post
        first_post_id = posts[0].get('id')
        print(f"\n--- Testing detailed comment fetch on first post ---")
        comments_data = self.get_post_comments(first_post_id, limit=100)

        if comments_data:
            comments = comments_data.get('data', [])
            print(f"\nComment Details (showing first 3):")
            for i, comment in enumerate(comments[:3], 1):
                print(f"\nComment {i}:")
                print(f"  From: {comment.get('from', {}).get('name', 'Unknown')}")
                print(f"  Time: {comment.get('created_time')}")
                print(f"  Message: {comment.get('message', 'No message')[:100]}...")
                print(f"  Permalink: {comment.get('permalink_url', 'N/A')}")

    def check_rate_limits(self):
        """Check current rate limit status"""
        print("\n" + "=" * 80)
        print("TEST 5: Rate Limit Check")
        print("=" * 80)

        # Make a simple request and check headers
        url = f'{self.base_url}/{self.user_id}'
        params = {'access_token': self.access_token}

        try:
            response = requests.get(url, params=params)

            # Facebook includes rate limit info in headers
            usage = response.headers.get('X-Business-Use-Case-Usage', 'Not available')
            app_usage = response.headers.get('X-App-Usage', 'Not available')

            print(f"Business Use Case Usage: {usage}")
            print(f"App Usage: {app_usage}")
            print("\nNote: Facebook limits to ~200 requests/hour per user")
        except Exception as e:
            print(f"Could not check rate limits: {e}")


def run_all_tests():
    """Run complete test suite"""
    print("\n" + "=" * 80)
    print("ALOHA AI WATCHTOWER - Facebook Graph API Test Suite")
    print("=" * 80)

    try:
        api = FacebookGraphAPI()

        # Run tests in sequence
        test_results = {
            'Basic Access': api.test_basic_access(),
            'Group Access': api.test_group_access(),
        }

        # Only continue if basic tests pass
        if test_results['Basic Access'] and test_results['Group Access']:
            api.test_full_workflow()
            api.check_rate_limits()

        # Summary
        print("\n" + "=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        for test, result in test_results.items():
            status = "✓ PASSED" if result else "✗ FAILED"
            print(f"{test}: {status}")

        if all(test_results.values()):
            print("\n✓ All tests passed! Ready for Sprint 2 development.")
        else:
            print("\n✗ Some tests failed. Check error messages above.")

    except ValueError as e:
        print(f"\n✗ Configuration Error: {e}")
        print("\nMake sure you have a .env file with:")
        print("  FACEBOOK_ACCESS_TOKEN=your_token_here")
        print("  HAWAII_TRACKER_GROUP_ID=your_group_id_here")
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")


if __name__ == '__main__':
    run_all_tests()