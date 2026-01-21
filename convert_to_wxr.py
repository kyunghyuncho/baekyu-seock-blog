
import os
import glob
import markdown
import yaml
import re
from datetime import datetime
from html import escape

# Configuration
BACKUP_DIR = "backup/posts"
IMAGE_BASE_URL = "http://localhost:8000" # Local server for import
OUTPUT_FILE = "tistory_backup.xml"

def create_wxr_header():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0"
	xmlns:excerpt="http://wordpress.org/export/1.2/excerpt/"
	xmlns:content="http://purl.org/rss/1.0/modules/content/"
	xmlns:wfw="http://wellformedweb.org/CommentAPI/"
	xmlns:dc="http://purl.org/dc/elements/1.1/"
	xmlns:wp="http://wordpress.org/export/1.2/"
>
<channel>
	<title>Tistory Backup</title>
	<link>http://localhost</link>
	<description>Backup of Kicho Tistory</description>
	<pubDate>{now}</pubDate>
	<language>ko-KR</language>
	<wp:wxr_version>1.2</wp:wxr_version>
	<wp:base_site_url>http://localhost</wp:base_site_url>
	<wp:base_blog_url>http://localhost</wp:base_blog_url>

"""

def create_wxr_footer():
    return """
</channel>
</rss>
"""

def parse_markdown_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split Frontmatter
    parts = content.split('---', 2)
    if len(parts) < 3:
        return None
    
    frontmatter_raw = parts[1].strip()
    markdown_body = parts[2]
    
    # Manual Frontmatter Parsing (Robust to invalid YAML quotes)
    meta = {}
    for line in frontmatter_raw.split('\n'):
        if ':' in line:
            key, val = line.split(':', 1)
            key = key.strip()
            val = val.strip()
            # Remove outer quotes if likely wrapping
            if len(val) >= 2 and val.startswith('"') and val.endswith('"'):
                val = val[1:-1]
            elif len(val) >= 2 and val.startswith("'") and val.endswith("'"):
                val = val[1:-1]
            meta[key] = val

    # Convert Markdown to HTML
    html_body = markdown.markdown(markdown_body)

    # Fix relative image paths to localhost URL
    # Replace src="../images/ID/foo.jpg" with src="http://localhost:8000/images/ID/foo.jpg"
    
    def replacer(match):
        path = match.group(1)
        # remove ../
        clean_path = path.replace('../', '')
        return f'src="{IMAGE_BASE_URL}/{clean_path}"'
        
    html_body = re.sub(r'src="(\.\./[^"]+)"', replacer, html_body)

    return {
        "title": meta.get('title', 'Untitled'),
        "post_id": meta.get('id', 0),
        "date": meta.get('date', ''), 
        "category": meta.get('category', 'Uncategorized'),
        "content_html": html_body,
        "original_url": meta.get('url', '')
    }

def format_date(date_str):
    # Expect "2021. 7. 19. 23:31" or similar
    try:
        dt = datetime.strptime(date_str, "%Y. %m. %d. %H:%M")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        # Try simplified if seconds missing or different format
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def create_item(post):
    title = escape(post['title'])
    content = escape(post['content_html'])
    post_id = post['post_id']
    date_str = format_date(post['date'])
    category = escape(post['category'])
    
    # Publii uses <content:encoded>, <wp:post_date>, <title>, <wp:status>publish</wp:status>
    # <wp:post_type>post</wp:post_type>
    
    return f"""
	<item>
		<title>{title}</title>
		<link>{post['original_url']}</link>
		<pubDate>{date_str}</pubDate>
		<dc:creator><![CDATA[admin]]></dc:creator>
		<guid isPermaLink="false">http://localhost/?p={post_id}</guid>
		<description></description>
		<content:encoded><![CDATA[{post['content_html']}]]></content:encoded>
		<excerpt:encoded><![CDATA[]]></excerpt:encoded>
		<wp:post_id>{post_id}</wp:post_id>
		<wp:post_date>{date_str}</wp:post_date>
		<wp:post_date_gmt>{date_str}</wp:post_date_gmt>
		<wp:comment_status>open</wp:comment_status>
		<wp:ping_status>open</wp:ping_status>
		<wp:post_name>post-{post_id}</wp:post_name>
		<wp:status>publish</wp:status>
		<wp:post_parent>0</wp:post_parent>
		<wp:menu_order>0</wp:menu_order>
		<wp:post_type>post</wp:post_type>
		<wp:post_password></wp:post_password>
		<wp:is_sticky>0</wp:is_sticky>
		<category domain="category" nicename="{category}"><![CDATA[{category}]]></category>
	</item>
"""

def main():
    print("Starting conversion...")
    
    # Read files
    files = glob.glob(os.path.join(BACKUP_DIR, "*.md"))
    files.sort(key=lambda x: int(os.path.basename(x).split('.')[0]))
    
    print(f"Found {len(files)} files.")
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as outfile:
        outfile.write(create_wxr_header())
        
        for f in files:
            post = parse_markdown_file(f)
            if post:
                outfile.write(create_item(post))
                
        outfile.write(create_wxr_footer())
        
    print(f"Conversion complete. Saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
