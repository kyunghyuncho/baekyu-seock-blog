import os
import glob
import markdown
import yaml
import re
from datetime import datetime
from xml.sax.saxutils import escape

# Configuration
POSTS_DIR = 'backup_naver/posts'
IMAGES_BASE_URL = 'https://kyunghyuncho.github.io/baekyu-seock-blog/backup_naver/images/'
OUTPUT_FILE = 'wordpress_import_naver.xml'

def parse_date(date_str):
    """Parses date string like '2007. 4. 10. 11:32' to 'YYYY-MM-DD HH:MM:SS'."""
    try:
        # Normalize spaces
        date_str = re.sub(r'\s+', ' ', date_str).strip()
        # Naver sometimes has just date "2026. 1. 19."
        if len(date_str.split('.')) == 4: # e.g. "2026. 1. 19."
             dt = datetime.strptime(date_str, '%Y. %m. %d.')
             return dt.strftime('%Y-%m-%d %H:%M:%S')
             
        dt = datetime.strptime(date_str, '%Y. %m. %d. %H:%M')
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except ValueError:
        try:
             # Try without spaces after dots just in case
            dt = datetime.strptime(date_str, '%Y.%m.%d. %H:%M')
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            print(f"Warning: Could not parse date '{date_str}', using current time.")
            return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def process_markdown_content(md_content, post_id):
    """Converts Markdown to HTML and fixes image links."""
    # Convert image links first
    # Pattern: ![alt](../images/ID/filename) -> ![alt](HTTPS_URL/ID/filename)
    
    # To track and deduplicate images within this post
    seen_images = set()

    def image_replacer(match):
        alt_text = match.group(1)
        relative_path = match.group(2)
        new_url = None
        
        # Check if path starts with ../images/ or just images/
        if '/images/' in relative_path:
            # We assume the path structure is consistent with what we saw
            # Extract everything after 'images/'
            parts = relative_path.split('/images/')
            if len(parts) > 1:
                path_suffix = parts[1] # e.g. "19/file:///.../foo.jpg" or "6/foo.jpg"
                
                # Robust cleaning: extract directory (ID) and filename
                segments = path_suffix.split('/')
                if len(segments) >= 2:
                     # folder is likely the first segment (post_id)
                     # filename is the last segment
                     folder = segments[0]
                     filename = segments[-1]
                     new_url = f'{IMAGES_BASE_URL}{folder}/{filename}'
                else:
                    # Fallback if structure is weird (e.g. just filename?)
                    new_url = f'{IMAGES_BASE_URL}{path_suffix}'
        
        # If we constructed a new URL, check for duplicates
        if new_url:
            if new_url in seen_images:
                return '' # Remove duplicate image
            seen_images.add(new_url)
            return f'![{alt_text}]({new_url})'
                    
        return match.group(0)

    # Replace standard markdown image syntax
    content = re.sub(r'!\[(.*?)\]\((.*?)\)', image_replacer, md_content)
    
    # Using markdown library to convert to HTML
    html = markdown.markdown(content, extensions=['tables', 'fenced_code'])
    
    # Add responsive styling to all img tags
    # Regex replace <img ... > with <img ... style="max-width: 100%; height: auto;">
    # avoiding duplicate style attributes if possible, but simple injection is safer for generated content
    html = re.sub(r'<img\s+', '<img style="max-width: 100%; height: auto;" ', html)
    
    return html

def generate_xml():
    xml_header = """<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0"
	xmlns:excerpt="http://wordpress.org/export/1.2/excerpt/"
	xmlns:content="http://purl.org/rss/1.0/modules/content/"
	xmlns:wfw="http://wellformedweb.org/CommentAPI/"
	xmlns:dc="http://purl.org/dc/elements/1.1/"
	xmlns:wp="http://wordpress.org/export/1.2/"
>
<channel>
	<title>Baekyu Seock Blog Backup (Naver)</title>
	<link>https://kyunghyuncho.github.io/baekyu-seock-blog/</link>
	<description>Backup of Naver Blog</description>
	<pubDate>Tue, 21 Jan 2026 00:00:00 +0000</pubDate>
	<language>ko-KR</language>
	<wp:wxr_version>1.2</wp:wxr_version>
	<wp:base_site_url>https://kyunghyuncho.github.io/baekyu-seock-blog/</wp:base_site_url>
	<wp:base_blog_url>https://kyunghyuncho.github.io/baekyu-seock-blog/</wp:base_blog_url>
    <wp:author><wp:author_id>1</wp:author_id><wp:author_login>admin</wp:author_login><wp:author_email>admin@example.com</wp:author_email><wp:author_display_name><![CDATA[admin]]></wp:author_display_name><wp:author_first_name><![CDATA[]]></wp:author_first_name><wp:author_last_name><![CDATA[]]></wp:author_last_name></wp:author>
"""
    
    xml_footer = """
</channel>
</rss>
"""
    
    items_xml = []
    
    if not os.path.exists(POSTS_DIR):
        print(f"Error: Posts directory {POSTS_DIR} does not exist.")
        return

    md_files = glob.glob(os.path.join(POSTS_DIR, '*.md'))
    print(f"Found {len(md_files)} posts.")
    
    for file_path in md_files:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Parse Frontmatter
        try:
            # Split by first two ---
            parts = re.split(r'^---$', content, maxsplit=2, flags=re.MULTILINE)
            if len(parts) < 3:
                print(f"Skipping {file_path}: Invalid frontmatter format")
                continue
                
            frontmatter_raw = parts[1]
            markdown_body = parts[2]
            
            try:
                metadata = yaml.safe_load(frontmatter_raw)
            except yaml.YAMLError:
                # Fallback manual parsing for titles with unescaped quotes
                metadata = {}
                for line in frontmatter_raw.splitlines():
                    if ':' in line:
                        key, value = line.split(':', 1)
                        key = key.strip()
                        value = value.strip()
                        # Remove outer quotes if present
                        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                            value = value[1:-1]
                        metadata[key] = value
            
            post_id = metadata.get('id', 0)
            title = metadata.get('title', 'Untitled')
            date_str = metadata.get('date', '')
            category = metadata.get('category', 'Uncategorized')
            original_url = metadata.get('url', '')
            
            formatted_date = parse_date(str(date_str))
            html_content = process_markdown_content(markdown_body, post_id)
            
            item = f"""
	<item>
		<title>{escape(str(title))}</title>
		<link>{original_url}</link>
		<pubDate>{formatted_date}</pubDate>
		<dc:creator><![CDATA[admin]]></dc:creator>
		<guid isPermaLink="false">{original_url}</guid>
		<description></description>
		<content:encoded><![CDATA[{html_content}]]></content:encoded>
		<excerpt:encoded><![CDATA[]]></excerpt:encoded>
		<wp:post_id>{post_id}</wp:post_id>
		<wp:post_date>{formatted_date}</wp:post_date>
		<wp:post_date_gmt>{formatted_date}</wp:post_date_gmt>
		<wp:comment_status>open</wp:comment_status>
		<wp:ping_status>open</wp:ping_status>
		<wp:post_name>post-{post_id}</wp:post_name>
		<wp:status>publish</wp:status>
		<wp:post_parent>0</wp:post_parent>
		<wp:menu_order>0</wp:menu_order>
		<wp:post_type>post</wp:post_type>
		<wp:post_password></wp:post_password>
		<wp:is_sticky>0</wp:is_sticky>
		<category domain="category" nicename="{escape(category)}"><![CDATA[{escape(category)}]]></category>
	</item>
"""
            items_xml.append(item)
            
        except Exception as e:
            print(f"Error processing {file_path}: {e}")
            
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(xml_header + "".join(items_xml) + xml_footer)
        
    print(f"Successfully generated {OUTPUT_FILE}")

if __name__ == "__main__":
    generate_xml()
