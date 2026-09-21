from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ..models import PageNode, Transition


class HtmlExportError(Exception):
    """Erro ao gerar um snapshot HTML do SpiderView."""


class HtmlExporter:
    SENSITIVE_KEYS = {
        "authorization", "proxy-authorization", "cookie", "set-cookie",
        "password", "passwd", "secret", "token", "access_token",
        "refresh_token", "api_key", "apikey", "session", "sessionid",
        "csrf", "xsrf",
    }

    def export(
        self,
        output_path: str | Path,
        nodes: Iterable[PageNode],
        transitions: Iterable[Transition],
        *,
        title: str = "SpiderView Investigation",
        redact_sensitive: bool = True,
    ) -> Path:
        path = Path(output_path).expanduser()
        try:
            payload = {
                "title": title,
                "nodes": [
                    self._serialize_node(node, redact_sensitive=redact_sensitive)
                    for node in nodes
                ],
                "transitions": [
                    self._serialize_transition(edge, redact_sensitive=redact_sensitive)
                    for edge in transitions
                ],
                "export": {
                    "format": "spiderview-html",
                    "version": 1,
                    "redacted": bool(redact_sensitive),
                },
            }
            payload_json = json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
                default=str,
            ).replace("</", "<\\/")
            html = _HTML_TEMPLATE.replace("__SPIDERVIEW_PAYLOAD__", payload_json)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(html, encoding="utf-8")
        except (OSError, TypeError, ValueError) as exc:
            raise HtmlExportError(f"Não foi possível exportar o HTML: {exc}") from exc
        return path

    def _serialize_node(self, node: PageNode, *, redact_sensitive: bool) -> dict:
        data = node.to_dict()
        data["url"] = self._redact_url(node.url) if redact_sensitive else node.url
        data["metadata"] = self._redact_value(node.metadata) if redact_sensitive else node.metadata
        data["preview_data_uri"] = self._preview_data_uri(node.preview_path)
        export_kind = str(
            (node.metadata or {}).get(
                "export_kind",
                "",
            )
            or ""
        ).strip().lower()

        if export_kind == "group":
            data["kind"] = "group"
            data["width"], data["height"] = 300, 178
        elif node.kind.value == "note":
            data["width"], data["height"] = 310, 190
        else:
            data["width"], data["height"] = 320, 250
        return data

    def _serialize_transition(self, transition: Transition, *, redact_sensitive: bool) -> dict:
        data = transition.to_dict()
        data["metadata"] = (
            self._redact_value(transition.metadata)
            if redact_sensitive else transition.metadata
        )
        return data

    def _preview_data_uri(self, preview_path: str | None) -> str | None:
        if not preview_path:
            return None
        path = Path(preview_path).expanduser()
        if not path.is_file():
            return None
        try:
            raw = path.read_bytes()
        except OSError:
            return None
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"

    def _redact_value(self, value, key: str = ""):
        if key.casefold() in self.SENSITIVE_KEYS:
            return "[REDACTED]"
        if isinstance(value, dict):
            return {str(k): self._redact_value(v, str(k)) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._redact_value(v, key) for v in value]
        return value

    def _redact_url(self, url: str) -> str:
        try:
            parts = urlsplit(url)
            query = parse_qsl(parts.query, keep_blank_values=True)
        except ValueError:
            return url
        if not query:
            return url
        redacted = []
        for key, value in query:
            if key.casefold() in self.SENSITIVE_KEYS:
                value = "[REDACTED]"
            redacted.append((key, value))
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(redacted), parts.fragment)
        )


_HTML_TEMPLATE = r'''<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SpiderView Investigation</title>
<style>
:root{color-scheme:dark;font-family:Inter,Segoe UI,system-ui,sans-serif}*{box-sizing:border-box}
html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#111419;color:#e8edf3}body{display:grid;grid-template-rows:56px 1fr}
header{display:flex;align-items:center;gap:8px;padding:0 14px;background:#1a1f26;border-bottom:1px solid #303842;z-index:10}.brand{font-weight:700}.muted{color:#8e99a8;font-size:12px}.spacer{flex:1}
input{width:min(360px,28vw);background:#11151b;border:1px solid #3a434e;color:#e8edf3;border-radius:8px;padding:8px 10px}button{background:#242b34;border:1px solid #414b58;color:#dce3eb;border-radius:8px;padding:7px 10px;cursor:pointer}button.active{background:#35587f;border-color:#6ca7e8}
#app{min-height:0;display:grid;grid-template-columns:1fr 340px}#viewport{position:relative;overflow:hidden;background:#14171c;cursor:grab;user-select:none}#viewport.panning{cursor:grabbing}#world{position:absolute;left:0;top:0;transform-origin:0 0}#edges{position:absolute;left:0;top:0;overflow:visible;pointer-events:none}
.edge{fill:none;stroke:#56616f;stroke-width:2}.edge-label{fill:#9da8b5;font-size:11px;paint-order:stroke;stroke:#14171c;stroke-width:4px;stroke-linejoin:round}
.card{position:absolute;border-radius:12px;background:#20252c;border:1.5px solid #404955;box-shadow:0 5px 15px #0006;overflow:hidden;cursor:grab;touch-action:none}.card.dragging{cursor:grabbing;z-index:20;box-shadow:0 10px 28px #0009}.card.selected{border:2.5px solid #60a5fa}.card.hidden{display:none}.card.note{background:#24231f;border-color:#d9a441}.card.group{background:#20262e;border-color:#46515e}.group .card-head{background:#2a323d}.note-strip{position:absolute;left:0;top:0;bottom:0;width:7px;background:#d9a441}
.card-head{height:50px;padding:10px 14px;background:#292e36;border-bottom:1px solid #353c46}.note .card-head{background:#302d25;padding-left:20px}.card-title{font-weight:650;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding-right:64px}.badge{position:absolute;right:12px;top:12px;border-radius:5px;padding:4px 7px;font-size:11px;font-weight:700;background:#3b82f6}.url{font-size:11px;color:#9ca3af;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:3px}
.preview{margin:10px 12px;height:132px;border-radius:8px;background:#15191e;display:flex;align-items:center;justify-content:center;overflow:hidden}.preview img{max-width:100%;max-height:100%;object-fit:contain}.card-foot{position:absolute;left:12px;right:12px;bottom:0;height:38px;border-top:1px solid #343a43;padding-top:9px;color:#9ca3af;font-size:11px;display:flex;justify-content:space-between}.note-body{padding:14px 20px 38px;color:#d6d0c2;font-size:13px;line-height:1.4;white-space:pre-wrap;overflow:hidden;height:132px}.note-tags{position:absolute;left:20px;right:12px;bottom:12px;color:#afa58f;font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
aside{background:#181d23;border-left:1px solid #303842;padding:16px;overflow:auto}aside h2{margin:0 0 4px;font-size:18px}aside h3{margin:18px 0 8px;font-size:13px;color:#aab5c2;text-transform:uppercase;letter-spacing:.06em}.kv{display:grid;grid-template-columns:84px 1fr;gap:7px 8px;font-size:12px}.kv .k{color:#8994a2}.kv .v{word-break:break-word}pre{white-space:pre-wrap;word-break:break-word;background:#101419;border:1px solid #303842;border-radius:8px;padding:10px;font-size:11px}#empty{color:#8d98a6;font-size:13px}#legend{position:absolute;left:14px;bottom:14px;background:#171c22dd;border:1px solid #323a45;border-radius:9px;padding:8px 10px;font-size:11px;color:#aeb8c4;pointer-events:none}
</style></head>
<body>
<header><div><div class="brand" id="title"></div><div class="muted" id="stats"></div></div><div class="spacer"></div><input id="search" placeholder="Buscar URL, título, endpoint ou domínio"><button data-kind="page" class="kind active">Page</button><button data-kind="api" class="kind active">API</button><button data-kind="dom_state" class="kind active">DOM</button><button data-kind="note" class="kind active">Note</button><button data-kind="group" class="kind active">Group</button><button id="fit">Fit</button></header>
<div id="app"><div id="viewport"><div id="world"><svg id="edges"></svg><div id="cards"></div></div><div id="legend">Scroll: zoom · Arraste o fundo: pan · Arraste um card: mover · Clique: detalhes</div></div><aside id="details"><div id="empty">Selecione um card para ver os detalhes.</div></aside></div>
<script>
const DATA=__SPIDERVIEW_PAYLOAD__;
const viewport=document.getElementById('viewport'),world=document.getElementById('world'),cardsLayer=document.getElementById('cards'),svg=document.getElementById('edges'),details=document.getElementById('details'),search=document.getElementById('search');
document.getElementById('title').textContent=DATA.title||'SpiderView Investigation';document.getElementById('stats').textContent=`${DATA.nodes.length} nodes · ${DATA.transitions.length} transitions${DATA.export.redacted?' · dados sensíveis redigidos':''}`;
const state={scale:1,tx:0,ty:0,panning:false,lastX:0,lastY:0,selected:null,kinds:new Set(['page','api','dom_state','note','group']),query:'',cardDrag:null};const nodeMap=new Map(DATA.nodes.map(n=>[n.id,n]));let minX=Infinity,minY=Infinity,maxX=0,maxY=0;
for(const n of DATA.nodes){minX=Math.min(minX,+n.x||0);minY=Math.min(minY,+n.y||0)}if(!isFinite(minX)){minX=0;minY=0}for(const n of DATA.nodes){n._x=(+n.x||0)-minX+140;n._y=(+n.y||0)-minY+140;maxX=Math.max(maxX,n._x+(n.width||320));maxY=Math.max(maxY,n._y+(n.height||250))}let WORLD_W=Math.max(1600,maxX+700),WORLD_H=Math.max(1000,maxY+700);function resizeWorld(width,height){WORLD_W=Math.max(WORLD_W,Math.ceil(width));WORLD_H=Math.max(WORLD_H,Math.ceil(height));world.style.width=WORLD_W+'px';world.style.height=WORLD_H+'px';svg.setAttribute('width',WORLD_W);svg.setAttribute('height',WORLD_H)}resizeWorld(WORLD_W,WORLD_H);svg.innerHTML='<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#56616f"/></marker></defs>';const defs=svg.querySelector('defs'),noteMarkers=new Map();function noteMarker(color){const normalized=(color||'#D9A441').toLowerCase();if(noteMarkers.has(normalized))return noteMarkers.get(normalized);const id='noteArrow'+noteMarkers.size,marker=document.createElementNS('http://www.w3.org/2000/svg','marker');marker.setAttribute('id',id);marker.setAttribute('viewBox','0 0 10 10');marker.setAttribute('refX','9');marker.setAttribute('refY','5');marker.setAttribute('markerWidth','7');marker.setAttribute('markerHeight','7');marker.setAttribute('orient','auto-start-reverse');const path=document.createElementNS('http://www.w3.org/2000/svg','path');path.setAttribute('d','M 0 0 L 10 5 L 0 10 z');path.setAttribute('fill',normalized);marker.appendChild(path);defs.appendChild(marker);noteMarkers.set(normalized,id);return id};
function visible(n){if(!state.kinds.has(n.kind))return false;if(!state.query)return true;return [n.title,n.url,n.method,n.status,JSON.stringify(n.metadata||{})].join(' ').toLowerCase().includes(state.query)}
function startCardDrag(e,n,el){if(e.button!==0)return;e.stopPropagation();state.cardDrag={id:n.id,pointerId:e.pointerId,startX:e.clientX,startY:e.clientY,nodeX:n._x,nodeY:n._y,moved:false};el.classList.add('dragging');el.setPointerCapture(e.pointerId);selectNode(n.id)}function moveCardDrag(e,n,el){const drag=state.cardDrag;if(!drag||drag.id!==n.id||drag.pointerId!==e.pointerId)return;const dx=(e.clientX-drag.startX)/state.scale,dy=(e.clientY-drag.startY)/state.scale;if(!drag.moved&&Math.hypot(dx,dy)>=3)drag.moved=true;n._x=Math.max(20,drag.nodeX+dx);n._y=Math.max(20,drag.nodeY+dy);el.style.left=n._x+'px';el.style.top=n._y+'px';resizeWorld(n._x+(n.width||320)+500,n._y+(n.height||250)+500);renderEdges();e.preventDefault()}function endCardDrag(e,n,el){const drag=state.cardDrag;if(!drag||drag.id!==n.id||drag.pointerId!==e.pointerId)return;n._suppressClick=drag.moved;state.cardDrag=null;el.classList.remove('dragging');if(el.hasPointerCapture(e.pointerId))el.releasePointerCapture(e.pointerId);e.stopPropagation()}function renderCards(){cardsLayer.innerHTML='';for(const n of DATA.nodes){const el=document.createElement('div');el.className='card '+(n.kind==='note'?'note ':'')+(visible(n)?'':'hidden');el.dataset.id=n.id;Object.assign(el.style,{left:n._x+'px',top:n._y+'px',width:(n.width||320)+'px',height:(n.height||250)+'px'});if(n.kind==='note'){const accent=(n.metadata&&n.metadata.color)||'#D9A441';el.style.borderColor=accent;const strip=document.createElement('div');strip.className='note-strip';strip.style.background=accent;el.appendChild(strip);const head=document.createElement('div');head.className='card-head';const title=document.createElement('div');title.className='card-title';title.textContent=n.title||'Nota';head.appendChild(title);el.appendChild(head);const body=document.createElement('div');body.className='note-body';body.textContent=(n.metadata&&n.metadata.note_text)||'Nota sem texto.';el.appendChild(body);const tags=document.createElement('div');tags.className='note-tags';tags.textContent=((n.metadata&&n.metadata.tags)||[]).map(t=>'#'+t).join('  ');el.appendChild(tags)}else if(n.kind==='group'){el.classList.add('group');const head=document.createElement('div');head.className='card-head';const title=document.createElement('div');title.className='card-title';title.textContent=n.title||'Group';head.appendChild(title);el.appendChild(head);const body=document.createElement('div');body.className='note-body';const count=(n.metadata&&n.metadata.count)||(n.metadata&&n.metadata.member_count)||0;const kind=(n.metadata&&n.metadata.group_kind)||(n.metadata&&n.metadata.view_group_kind)||'group';body.textContent=String(count)+' item(s) · '+kind;el.appendChild(body)}else{const head=document.createElement('div');head.className='card-head';const title=document.createElement('div');title.className='card-title';title.textContent=n.title||n.url||'(sem título)';const url=document.createElement('div');url.className='url';url.textContent=n.url||'';const badge=document.createElement('div');badge.className='badge';badge.textContent=(n.method||'GET').toUpperCase();head.append(title,url,badge);el.appendChild(head);const preview=document.createElement('div');preview.className='preview';if(n.preview_data_uri){const img=document.createElement('img');img.src=n.preview_data_uri;preview.appendChild(img)}else{preview.textContent='Preview indisponível';preview.style.color='#667085';preview.style.fontSize='12px'}el.appendChild(preview);const foot=document.createElement('div');foot.className='card-foot';const a=document.createElement('span');a.textContent='HTTP '+(n.status??'—');const b=document.createElement('span');b.textContent=n.kind;foot.append(a,b);el.appendChild(foot)}el.addEventListener('pointerdown',e=>startCardDrag(e,n,el));el.addEventListener('pointermove',e=>moveCardDrag(e,n,el));el.addEventListener('pointerup',e=>endCardDrag(e,n,el));el.addEventListener('pointercancel',e=>endCardDrag(e,n,el));el.addEventListener('click',e=>{e.stopPropagation();if(n._suppressClick){n._suppressClick=false;return}selectNode(n.id)});cardsLayer.appendChild(el)}renderEdges()}
function renderEdges(){[...svg.querySelectorAll('.edge,.edge-label')].forEach(x=>x.remove());for(const e of DATA.transitions){const s=nodeMap.get(e.source_id),t=nodeMap.get(e.target_id);if(!s||!t||!visible(s)||!visible(t))continue;const sx=s._x+(s.width||320)/2,sy=s._y+(s.height||250)/2,tx=t._x+(t.width||320)/2,ty=t._y+(t.height||250)/2,dx=Math.max(80,Math.abs(tx-sx)*.45),sign=Math.sign(tx-sx||1);const p=document.createElementNS('http://www.w3.org/2000/svg','path');p.setAttribute('class','edge');const isNote=Boolean(e.metadata&&e.metadata.manual_note);const noteColor=isNote?((e.metadata&&e.metadata.note_color)||(s.metadata&&s.metadata.color)||'#D9A441'):null;p.setAttribute('marker-end',isNote?'url(#'+noteMarker(noteColor)+')':'url(#arrow)');if(isNote){p.setAttribute('stroke',noteColor);p.setAttribute('stroke-dasharray','8 6')}p.setAttribute('d',`M ${sx} ${sy} C ${sx+sign*dx} ${sy}, ${tx-sign*dx} ${ty}, ${tx} ${ty}`);svg.appendChild(p);if(e.label){const label=document.createElementNS('http://www.w3.org/2000/svg','text');label.setAttribute('class','edge-label');label.setAttribute('x',(sx+tx)/2);label.setAttribute('y',(sy+ty)/2-6);label.setAttribute('text-anchor','middle');label.textContent=e.label;svg.appendChild(label)}}}
function selectNode(id){state.selected=id;document.querySelectorAll('.card').forEach(el=>el.classList.toggle('selected',el.dataset.id===id));const n=nodeMap.get(id);if(!n)return;details.innerHTML='';const h=document.createElement('h2');h.textContent=n.title||'(sem título)';const sub=document.createElement('div');sub.className='muted';sub.textContent=n.kind;details.append(h,sub);const h3=document.createElement('h3');h3.textContent='Node';details.appendChild(h3);const kv=document.createElement('div');kv.className='kv';[['URL',n.url||'—'],['Method',n.method||'—'],['Status',n.status??'—'],['ID',n.id]].forEach(([k,v])=>{const a=document.createElement('div');a.className='k';a.textContent=k;const b=document.createElement('div');b.className='v';b.textContent=String(v);kv.append(a,b)});details.appendChild(kv);if(n.kind==='note'&&n.metadata&&n.metadata.note_text){const nh=document.createElement('h3');nh.textContent='Nota';const p=document.createElement('pre');p.textContent=n.metadata.note_text;details.append(nh,p)}const mh=document.createElement('h3');mh.textContent='Metadata';const pre=document.createElement('pre');pre.textContent=JSON.stringify(n.metadata||{},null,2);details.append(mh,pre);const incoming=DATA.transitions.filter(e=>e.target_id===id),outgoing=DATA.transitions.filter(e=>e.source_id===id),rh=document.createElement('h3');rh.textContent=`Relações · ${incoming.length} in / ${outgoing.length} out`;const rel=document.createElement('pre');rel.textContent=[...incoming.map(e=>'← '+(nodeMap.get(e.source_id)?.title||e.source_id)+'  '+(e.label||e.type)),...outgoing.map(e=>'→ '+(nodeMap.get(e.target_id)?.title||e.target_id)+'  '+(e.label||e.type))].join('\n')||'Nenhuma';details.append(rh,rel)}
function transform(){world.style.transform=`translate(${state.tx}px,${state.ty}px) scale(${state.scale})`}function fit(){const vw=viewport.clientWidth,vh=viewport.clientHeight,scale=Math.min((vw-70)/WORLD_W,(vh-70)/WORLD_H,1);state.scale=Math.max(.05,scale);state.tx=(vw-WORLD_W*state.scale)/2;state.ty=(vh-WORLD_H*state.scale)/2;transform()}
viewport.addEventListener('wheel',e=>{e.preventDefault();const r=viewport.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top,old=state.scale,next=Math.min(4.5,Math.max(.05,old*(e.deltaY<0?1.14:1/1.14))),wx=(mx-state.tx)/old,wy=(my-state.ty)/old;state.scale=next;state.tx=mx-wx*next;state.ty=my-wy*next;transform()},{passive:false});viewport.addEventListener('pointerdown',e=>{if(e.target.closest&&e.target.closest('.card'))return;state.panning=true;state.lastX=e.clientX;state.lastY=e.clientY;viewport.classList.add('panning');viewport.setPointerCapture(e.pointerId)});viewport.addEventListener('pointermove',e=>{if(!state.panning)return;state.tx+=e.clientX-state.lastX;state.ty+=e.clientY-state.lastY;state.lastX=e.clientX;state.lastY=e.clientY;transform()});viewport.addEventListener('pointerup',()=>{state.panning=false;viewport.classList.remove('panning')});search.addEventListener('input',()=>{state.query=search.value.trim().toLowerCase();renderCards()});document.querySelectorAll('.kind').forEach(btn=>btn.addEventListener('click',()=>{const k=btn.dataset.kind;if(state.kinds.has(k)){state.kinds.delete(k);btn.classList.remove('active')}else{state.kinds.add(k);btn.classList.add('active')}renderCards()}));document.getElementById('fit').addEventListener('click',fit);renderCards();requestAnimationFrame(fit);
</script></body></html>'''
