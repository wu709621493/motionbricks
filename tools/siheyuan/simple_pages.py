# SPDX-License-Identifier: Apache-2.0
"""Static start pages and geometry illustrations; Python standard library only."""
from __future__ import annotations
import html
import math


def document(title, body):
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#f6f2e8;color:#233d35;font:17px/1.75 system-ui,sans-serif}}main{{max-width:1000px;margin:auto;padding:24px}}h1{{font-size:clamp(28px,5vw,42px);line-height:1.3}}h2{{font-size:23px;margin-top:32px}}a{{color:inherit;text-underline-offset:4px;overflow-wrap:anywhere}}a:focus-visible,summary:focus-visible{{outline:3px solid #a34a36;outline-offset:4px}}.notice{{border-left:4px solid #a34a36;padding:10px 16px;background:#ece3d0}}.links{{display:flex;flex-wrap:wrap;gap:12px}}.links a{{padding:10px 16px;background:#fcfbf5;border:1px solid #b8c6b1;border-radius:6px;text-decoration:none}}figure{{margin:20px 0}}img{{width:100%;height:auto;display:block;border:1px solid #d6d6c7;background:#fcfbf5}}figcaption,small{{color:#63705e;font-size:14px}}details{{border-top:1px solid #d6d6c7;padding:14px 0}}summary{{cursor:pointer}}article{{border-top:1px solid #d6d6c7;padding:12px 0}}code{{overflow-wrap:anywhere}}footer{{margin-top:32px;border-top:1px solid #d6d6c7;padding-top:14px}}@media(max-width:580px){{main{{padding:16px}}.links a{{flex:1 1 140px}}}}@media print{{body{{background:white}}.links{{display:block}}.links a{{display:block;border:0;padding:3px}}details{{display:none}}img{{max-height:65vh;object-fit:contain}}}}
</style></head><body><main>{body}</main></body></html>
'''


def pages(title, summary, overview, views, downloads, records, sources=()):
    """Only the overview image loads initially; other views are ordinary links."""
    def links(items, download=False):
        return '<div class="links">'+''.join(
            f'<a href="{html.escape(url,quote=True)}"'+(' download' if download else '')+
            f'>{html.escape(label)}</a>' for label,url in items)+'</div>'
    body=f'<small>MOTIONBRICKS · 图册版</small><h1>{html.escape(title)}</h1><p class="notice">{html.escape(summary)}</p>'
    body+='<h2>1. 看整体</h2>'
    body+=f'<figure><a href="{overview}"><img src="{overview}" alt="{html.escape(title)}：固定视角体量图，尺寸为假设" width="900" height="720"></a><figcaption>点图可单独打开。固定视角，无需拖动旋转。</figcaption></figure>'
    body+='<h2>2. 选一张图看细节</h2>'+links(views)
    body+='<p><a href="inventory.html">查看全部构件与说明</a></p>'
    body+='<h2>3. 留一份模型</h2>'+links(downloads,True)
    body+='<p><small>可用系统打印功能保存PDF。离线使用时，请保留同目录全部文件。</small></p>'
    body+='<details><summary>还想旋转看？打开交互实验版</summary><p><a href="interactive.html">进入可选交互版</a>。交互、移动端布局与键盘操作仍待实际浏览器验收。</p></details>'
    body+='<footer><small>构想：吴孟城（Windy Wu）；AI辅助建模。原创图形与数据 CC-BY-4.0；代码 Apache-2.0。</small></footer>'
    index=document(title,body)
    inventory=f'<a href="index.html">← 返回图册</a><h1>{html.escape(title)}：构件目录</h1><p>{html.escape(summary)}</p><p>共 {len(records)} 条记录。可用浏览器或阅读器的“查找”按名称搜索。</p>'
    for r in records:
        inventory+=f'<article id="{html.escape(r["id"],quote=True)}"><h2>{html.escape(r["name"])}</h2><p><code>{html.escape(r["id"])}</code></p><p>{html.escape(r["description"])}</p></article>'
    if sources:
        inventory+='<h2>来源索引</h2>'
        for s in sources:
            inventory+=f'<article><h3>{html.escape(s["id"])} · {html.escape(s["title"])}</h3><p>{html.escape(s["supports"])}</p><p>边界：{html.escape(s["limitations"])}</p><a href="{html.escape(s["url"],quote=True)}" rel="noopener noreferrer">原始来源（需联网）</a></article>'
    return {'index.html':index,'inventory.html':document(title+' · 构件目录',inventory)}


def massing_svg(parts, site, title, show_roofs=True):
    """Fixed 35-degree illustration with an automatically fitted viewBox."""
    w,d=site;c=math.cos(math.radians(35));s=math.sin(math.radians(35))
    def raw(v):
        x,y,z=v[0]-w/2,v[1]-d/2,v[2] if len(v)>2 else 0
        return c*x-s*y,-(s*x+c*y)*.5-z*1.2
    ground=[[0,0,0],[w,0,0],[w,d,0],[0,d,0]]
    all_points=[raw(v) for p in parts for v in p['vertices']]+[raw(v) for v in ground]
    xmin=min(p[0] for p in all_points);xmax=max(p[0] for p in all_points)
    ymin=min(p[1] for p in all_points);ymax=max(p[1] for p in all_points)
    scale=min(820/(xmax-xmin),540/(ymax-ymin))
    def points(vertices):
        return ' '.join(f'{450+(x-(xmin+xmax)/2)*scale:.2f},{375+(y-(ymin+ymax)/2)*scale:.2f}' for x,y in map(raw,vertices))
    out=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 720" role="img" aria-labelledby="title">',
         f'<title id="title">{html.escape(title)}；全部尺寸为假设</title>',
         '<rect width="900" height="720" fill="#f6f2e8"/>',
         f'<text x="30" y="42" font-size="24" fill="#233d35">{html.escape(title)}</text>',
         f'<polygon points="{points(ground)}" fill="#e6decb"/>']
    faces=[]
    for p in parts:
        if p['kind']=='roof' and not show_roofs:continue
        for face in p['faces']:
            vertices=[p['vertices'][j] for j in face]
            depth=sum(-s*v[0]-c*v[1]+v[2]*.2 for v in vertices)/len(vertices)
            faces.append((depth,p,vertices))
    for _,p,v in sorted(faces,key=lambda f:f[0]):
        out.append(f'<polygon data-element="{p["element"]}" points="{points(v)}" fill="{p["color"]}" stroke="#354f45" stroke-width=".65"/>')
    out.append('<text x="30" y="690" font-size="16" fill="#233d35">固定视角体量 · 非实测 · 非施工图</text></svg>')
    return '\n'.join(out)+'\n'
