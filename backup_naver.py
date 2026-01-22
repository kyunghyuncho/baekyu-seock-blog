import os
import requests
import json
import re
from bs4 import BeautifulSoup
from markdownify import markdownify as md
import argparse
import html
from urllib.parse import urlparse, unquote
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

def sanitize_filename(name):
    """Sanitize string to be safe for filenames."""
    if not name:
        return "untitled"
    return "".join([c for c in name if c.isalpha() or c.isdigit() or c in (' ', '-', '_')]).rstrip()

def download_image(url, save_dir):
    if not url.startswith(('http:', 'https:')):
        return url
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36",
            "Referer": "https://blog.naver.com/"
        }
        response = requests.get(url, stream=True, headers=headers)
        response.raise_for_status()
        
        # Extract filename from URL
        parsed = urlparse(url)
        filename = os.path.basename(unquote(parsed.path))
        if not filename or len(filename) > 50:
             # Naver images often have long cryptic names, or no extension in path
            filename = f"image_{int(time.time()*1000)}"

        # Handle extension using Content-Type header
        name, ext = os.path.splitext(filename)
        if not ext or len(ext) > 5: # basic sanity check
            content_type = response.headers.get('Content-Type', '').lower()
            if 'image/jpeg' in content_type or 'image/jpg' in content_type:
                ext = '.jpg'
            elif 'image/png' in content_type:
                ext = '.png'
            elif 'image/gif' in content_type:
                ext = '.gif'
            elif 'image/webp' in content_type:
                ext = '.webp'
            else:
                ext = '.jpg'
            
            filename = f"{name}{ext}"

        filepath = os.path.join(save_dir, filename)
        
        # Avoid duplicate downloads if possible (simple check)
        counter = 1
        base_name = name
        while os.path.exists(filepath):
             filename = f"{base_name}_{counter}{ext}"
             filepath = os.path.join(save_dir, filename)
             counter += 1

        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(1024):
                f.write(chunk)
        return filename
    except Exception as e:
        print(f"    [!] Error downloading image {url}: {e}")
        return url 

def get_post_list(blog_id, max_pages=100):
    """
    Fetches list of posts using Naver's async API.
    Returns a list of dicts with 'logNo', 'title', 'addDate'.
    """
    posts = []
    base_url = "https://blog.naver.com/PostTitleListAsync.naver"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36"
    }

    print(f"[*] Fetching post list for {blog_id}...")
    
    for page in range(1, max_pages + 1):
        params = {
            'blogId': blog_id,
            'viewdate': '',
            'currentPage': page,
            'categoryNo': '', 
            'parentCategoryNo': '',
            'countPerPage': 30
        }
        
        try:
            resp = requests.get(base_url, params=params, headers=headers)
            resp.raise_for_status()
            # Naver returns invalid JSON with \' escapes sometimes
            cleaned_text = resp.text.replace("\\'", "'")
            data = json.loads(cleaned_text)
            
            if 'postList' not in data:
                break
                
            current_posts = data['postList']
            if not current_posts:
                break
                
            for post in current_posts:
                # Naver titles are URL encoded sometimes
                title = unquote(post['title']).replace('+', ' ')
                # Also unescape HTML entities
                title = html.unescape(title)
                posts.append({
                    'logNo': post['logNo'],
                    'title': title,
                    'date': post['addDate']
                })
            
            print(f"    Page {page}: Found {len(current_posts)} posts (Total so far: {len(posts)})")
            
            # Helper logic to stop if we think we reached the end (naive check)
            if len(current_posts) < 30:
                break
                
        except Exception as e:
            print(f"[!] Error fetching post list page {page}: {e}")
            break
            
    return posts

def backup_post(blog_id, post_info, base_dir="backup_naver"):
    log_no = post_info['logNo']
    title = post_info['title']
    date = post_info['date']
    
    url = f"https://blog.naver.com/PostView.naver?blogId={blog_id}&logNo={log_no}"
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36"
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()
    except Exception as e:
        print(f"[!] Network error for {url}: {e}")
        return False

    soup = BeautifulSoup(response.text, 'html.parser')

    # Main content container
    # Naver SmartEditor 2.0 uses #post-view...
    # Naver SmartEditor One uses .se-main-container
    
    content_elem = soup.select_one('.se-main-container')
    if not content_elem:
        content_elem = soup.find(id=f"post-view{log_no}")
        
    if not content_elem:
        print(f"[-] Content not found for {log_no} ({title})")
        return False

    print(f"[+] Processing {log_no}: {title}")

    # Prepare directories
    post_dir = os.path.join(base_dir, "posts")
    img_dir = os.path.join(base_dir, "images", str(log_no))
    os.makedirs(post_dir, exist_ok=True)
    os.makedirs(img_dir, exist_ok=True)

    # Process Images
    if content_elem:
        # Download images
        for img in content_elem.find_all('img'):
            src = img.get('src')
            # Naver generic spacer images or icons
            if not src or 'blank' in src or 'pixel' in src:
                continue
                
            # SmartEditor lazy loading uses data-src or data-lazy-src
            if img.get('data-lazy-src'):
                src = img.get('data-lazy-src')
            elif img.get('data-src'):
                src = img.get('data-src')

            if src:
                # Do NOT remove query parameters as Naver images require them for access
                # and data-lazy-src usually points to a high-res version with correct params.

                filename = download_image(src, img_dir)
                # Replace src with local relative path
                img['src'] = f"../images/{log_no}/{filename}"
                # Remove srcset/data-src to force local usage
                if img.has_attr('srcset'): del img['srcset']
                if img.has_attr('data-src'): del img['data-src']
                if img.has_attr('data-lazy-src'): del img['data-lazy-src']
        
        # Convert to Markdown
        content_md = md(str(content_elem), heading_style="atx")
    else:
        content_md = ""

    # Frontmatter
    frontmatter = f"""---
title: "{title}"
date: "{date}"
id: {log_no}
url: "{url}"
---

"""
    
    filename = f"{log_no}.md"
    filepath = os.path.join(post_dir, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(frontmatter + content_md)

    return True

def main():
    parser = argparse.ArgumentParser(description="Backup Naver Blog")
    parser.add_argument("--blog_id", default="kicho_57", help="Naver Blog ID")
    parser.add_argument("--output", default="backup_naver", help="Output directory")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of posts to backup (0 for all)")
    parser.add_argument("--workers", type=int, default=5, help="Number of worker threads")
    args = parser.parse_args()

    # Get list of posts
    posts = get_post_list(args.blog_id)
    print(f"Total posts found: {len(posts)}")
    
    if args.limit > 0:
        posts = posts[:args.limit]
        print(f"Limiting to first {args.limit} posts.")

    success_count = 0
    
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_post = {executor.submit(backup_post, args.blog_id, p, args.output): p for p in posts}
        for future in as_completed(future_to_post):
            p = future_to_post[future]
            try:
                if future.result():
                    success_count += 1
            except Exception as e:
                print(f"[!] Error processing post {p['logNo']}: {e}")

    print(f"Backup complete. Successfully saved {success_count} posts to {args.output}")

if __name__ == "__main__":
    main()
