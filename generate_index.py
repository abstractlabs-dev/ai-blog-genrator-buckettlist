import os
import json
from pathlib import Path

def main():
    base_dir = Path("data/output/json")
    if not base_dir.exists():
        print("No json output directory found.")
        return
        
    articles = []
    # Find the 3 most recently created json files
    files = sorted(base_dir.glob("*.json"), key=os.path.getmtime, reverse=True)[:3]
    
    for f in files:
        with open(f, "r", encoding="utf-8") as file:
            data = json.load(file)
            articles.append(data)
            
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Generated Articles Review</title>
        <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; max-width: 1200px; margin: 0 auto; padding: 20px; background-color: #f4f7f6; color: #333; }
            h1.main-title { text-align: center; color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; margin-bottom: 30px; }
            .article-card { background: white; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom: 40px; padding: 30px; overflow: hidden; }
            .article-meta { background: #ecf0f1; padding: 15px; border-radius: 5px; margin-bottom: 20px; font-size: 0.9em; border-left: 4px solid #3498db; }
            .article-meta strong { color: #2980b9; }
            .content { padding: 20px 0; }
            img { max-width: 100%; height: auto; border-radius: 4px; }
            .featured-image img { width: 100%; max-height: 500px; object-fit: cover; }
            .nav-tabs { display: flex; list-style: none; padding: 0; margin-bottom: 20px; border-bottom: 1px solid #ddd; }
            .nav-tabs li { padding: 10px 20px; cursor: pointer; background: #eee; border: 1px solid #ddd; border-bottom: none; border-radius: 5px 5px 0 0; margin-right: 5px; }
            .nav-tabs li.active { background: white; border-bottom: 1px solid white; margin-bottom: -1px; font-weight: bold; }
        </style>
    </head>
    <body>
        <h1 class="main-title">AI Generated Articles Review Panel</h1>
        <ul class="nav-tabs" id="tabs">
    """
    
    for i, a in enumerate(articles):
        active = 'class="active"' if i == 0 else ''
        html_content += f'<li {active} onclick="showTab({i})">Article {i+1}</li>'
        
    html_content += "</ul>"
    
    for i, a in enumerate(articles):
        display = 'block' if i == 0 else 'none'
        
        title = a.get("title", "Untitled")
        word_count = len(a.get("article_content", "").split())
        seo_score = "N/A"
        content_html = a.get("article_content", "")
        keywords = a.get("keywords", [])
        meta_desc = a.get("meta_description", "")
        
        html_content += f"""
        <div id="article-{i}" class="article-card" style="display: {display};">
            <div class="article-meta">
                <p><strong>Title:</strong> {title}</p>
                <p><strong>Keywords:</strong> {', '.join(keywords)}</p>
                <p><strong>Word Count:</strong> {word_count} | <strong>SEO Score:</strong> {seo_score}</p>
                <p><strong>Meta Description:</strong> {meta_desc}</p>
            </div>
            <div class="content">
                {content_html}
            </div>
        </div>
        """
        
    html_content += """
        <script>
            function showTab(index) {
                // hide all
                document.querySelectorAll('.article-card').forEach(el => el.style.display = 'none');
                document.querySelectorAll('.nav-tabs li').forEach(el => el.classList.remove('active'));
                
                // show selected
                document.getElementById('article-' + index).style.display = 'block';
                document.querySelectorAll('.nav-tabs li')[index].classList.add('active');
            }
        </script>
    </body>
    </html>
    """
    
    with open("data/output/index.html", "w", encoding="utf-8") as f:
        f.write(html_content)
        
    print(f"Generated index.html with {len(articles)} articles.")

if __name__ == "__main__":
    main()
