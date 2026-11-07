#!/usr/bin/env python3
from pathlib import Path

root=Path(__file__).resolve().parents[1]
html=(root/'Web/index.html').read_text()
for name in ('data.js','engine.js','app.js'):
    script=(root/'Web'/name).read_text().replace('</script','<\\/script')
    html=html.replace(f'<script src="{name}"></script>',f'<script>\n{script}\n</script>')
assert '<script src=' not in html
(root/'Preview.html').write_text(html)
print('Generated standalone Preview.html.')
