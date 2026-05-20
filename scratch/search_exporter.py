import os

root_dir = r"C:\Users\10102\Downloads\codebase\ai-blog-generator-base-refactor-segmentation\ai-blog-generator-base-refactor-segmentation"
for root, dirs, files in os.walk(root_dir):
    for file in files:
        if file.endswith('.py') or file.endswith('.json'):
            path = os.path.join(root, file)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                if 'SocialExporter' in content:
                    print(f"Found 'SocialExporter' in {path}")
            except Exception as e:
                pass
