
import os
import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md
import time
import argparse
from urllib.parse import urlparse, unquote

def sanitize_filename(name):
    """Sanitize string to be safe for filenames."""
    return "".join([c for c in name if c.isalpha() or c.isdigit() or c in (' ', '-', '_')]).rstrip()

def download_image(url, save_dir):
    if not url.startswith(('http:', 'https:')):
        return url
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36",
            "Referer": "https://kicho.tistory.com/"
        }
        response = requests.get(url, stream=True, headers=headers)
        response.raise_for_status()
        
        # Extract filename from URL
        parsed = urlparse(url)
        filename = os.path.basename(unquote(parsed.path))
        if not filename:
            filename = "image_unknown.jpg"
            
        # Handle query parameters which might be part of the image generation/serving
        if 'fname=' in parsed.query:
             # Tistory sometimes puts the real url in fname param or similar mechanisms, 
             # but often the direct src is accessible. 
             # Let's try to just save what we get.
             pass

        # Handle extension using Content-Type header
        name, ext = os.path.splitext(filename)
        if not ext:
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
                # print(f"    [?] Unknown content type for {url}: {content_type}, defaulting to .jpg")
                ext = '.jpg'
            
            filename = f"{name}{ext}"
        
        # Tistory images sometimes look like /image/blabla
        if len(filename) > 50:
             filename = filename[-50:]

        filepath = os.path.join(save_dir, filename)
        
        if os.path.exists(filepath):
             # Try not to overwrite valid images, but also don't complicate too much
             return filename

        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(1024):
                f.write(chunk)
        return filename
    except Exception as e:
        print(f"    [!] Error downloading image {url}: {e}")
        return url # Return original URL if failed

def backup_post(post_id, base_dir="backup"):
    url = f"https://kicho.tistory.com/{post_id}"
    try:
        response = requests.get(url)
        if response.status_code == 404:
            # print(f"[-] Post {post_id} not found.")
            return False
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"[!] Network error for {url}: {e}")
        return False

    soup = BeautifulSoup(response.text, 'html.parser')

    # Selectors based on analysis
    title_elem = soup.select_one('.title, h3.title, .entry-title')
    date_elem = soup.select_one('.date, .time, .published')
    category_elem = soup.select_one('.category, .entry-category')
    content_elem = soup.select_one('.article, .entry-content, .tt_article_useless_p_margin')

    if not title_elem:
        # Might be a protected post or redirect
        # print(f"[-] Post {post_id} skipped (no title found).")
        return False

    title = title_elem.get_text(strip=True)
    date = date_elem.get_text(strip=True) if date_elem else ""
    category = category_elem.get_text(strip=True) if category_elem else "Uncategorized"
    
    # Clean category (remove brackets usually format like 'Category (5)')
    if '(' in category:
         category = category.split('(')[0].strip()

    print(f"[+] Processing {post_id}: {title}")

    # Prepare directories
    post_dir = os.path.join(base_dir, "posts")
    img_dir = os.path.join(base_dir, "images", str(post_id))
    os.makedirs(post_dir, exist_ok=True)
    os.makedirs(img_dir, exist_ok=True)

    # Process Images
    if content_elem:
        for img in content_elem.find_all('img'):
            src = img.get('src')
            if src:
                # Tistory often uses cfile*.uf.tistory.com...
                filename = download_image(src, img_dir)
                # Replace src with local relative path
                img['src'] = f"../images/{post_id}/{filename}"
                # Remove srcset to force local usage
                if img.has_attr('srcset'):
                    del img['srcset']
        
        # Convert to Markdown
        # Determine heading style (ATX is standard #)
        content_md = md(str(content_elem), heading_style="atx")
    else:
        content_md = ""

    # Frontmatter
    frontmatter = f"""---
title: "{title}"
date: "{date}"
category: "{category}"
id: {post_id}
url: "{url}"
---

"""
    
    filename = f"{post_id}.md"
    filepath = os.path.join(post_dir, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(frontmatter + content_md)

    return True

from concurrent.futures import ThreadPoolExecutor, as_completed

def main():
    parser = argparse.ArgumentParser(description="Backup Tistory Blog")
    parser.add_argument("--start", type=int, default=1, help="Start ID")
    parser.add_argument("--end", type=int, default=700, help="End ID")
    parser.add_argument("--output", default="backup", help="Output directory")
    parser.add_argument("--workers", type=int, default=10, help="Number of worker threads")
    args = parser.parse_args()

    print(f"Starting backup from ID {args.start} to {args.end} with {args.workers} workers...")
    
    post_ids = range(args.start, args.end + 1)
    found_count = 0
    
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_id = {executor.submit(backup_post, pid, args.output): pid for pid in post_ids}
        for future in as_completed(future_to_id):
            pid = future_to_id[future]
            try:
                if future.result():
                    found_count += 1
            except Exception as e:
                print(f"[!] Error processing post {pid}: {e}")

    print(f"Backup complete. Found {found_count} posts.")

if __name__ == "__main__":
    main()
