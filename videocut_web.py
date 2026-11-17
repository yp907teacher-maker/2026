#!/usr/bin/env python3
"""videocut 網頁介面（僅用標準函式庫）。

  python videocut_web.py [--port 8000] [--host 127.0.0.1]

開啟 http://127.0.0.1:8000 ，上傳影片、選功能、按執行，即可預覽與下載結果。
上傳與輸出檔放在 ./videocut_workspace/。
"""
import argparse
import contextlib
import io
import json
import os
import re
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

import videocut

WORK = os.path.join(os.getcwd(), "videocut_workspace")
LOCK = threading.Lock()  # 一次只跑一個 ffmpeg 任務
MAX_UPLOAD = 2 * 1024 ** 3

# 每個功能的欄位定義，前端依此產生表單
# kind: text / number / select / file；flag 為 None 表示位置參數
SPEC = {
    "auto": {"label": "⭐ 一鍵成片（勾選多支素材）", "out": "mp4", "multi": True, "fields": [
        {"name": "remove_silence", "flag": "--remove-silence", "label": "自動移除靜音", "kind": "check"},
        {"name": "duration", "flag": "--duration", "label": "快剪目標秒數（清空＝不縮短）", "kind": "number", "default": "15"},
        {"name": "preset", "flag": "--preset", "label": "輸出比例（留空＝不改）", "kind": "select",
         "options": ["", "9:16", "16:9", "1:1", "4:5"]},
        {"name": "mode", "flag": "--mode", "label": "比例方式", "kind": "select", "options": ["crop", "pad"]},
        {"name": "srt", "flag": "--srt", "label": "字幕 SRT（可不選）", "kind": "file", "optional": True},
        {"name": "music", "flag": "--music", "label": "背景音樂（可不選）", "kind": "file", "optional": True},
        {"name": "volume", "flag": "--volume", "label": "音樂音量 0~1", "kind": "number", "default": "0.3"}]},
    "info": {"label": "影片資訊", "out": None, "fields": []},
    "trim": {"label": "裁切", "out": "mp4", "fields": [
        {"name": "start", "flag": "-s", "label": "開始（秒或 mm:ss）", "kind": "text", "default": "0"},
        {"name": "end", "flag": "-e", "label": "結束（可留空）", "kind": "text"},
        {"name": "fast", "flag": "--fast", "label": "快速（不重新編碼）", "kind": "check"}]},
    "cut": {"label": "多段保留", "out": "mp4", "fields": [
        {"name": "keep", "flag": "--keep", "label": "保留區段，每行一段，如 0-5", "kind": "lines"}]},
    "concat": {"label": "合併（勾選多支）", "out": "mp4", "multi": True, "fields": []},
    "speed": {"label": "變速", "out": "mp4", "fields": [
        {"name": "factor", "flag": "-f", "label": "倍率", "kind": "number", "default": "2"}]},
    "resize": {"label": "改比例", "out": "mp4", "fields": [
        {"name": "preset", "flag": "--preset", "label": "比例", "kind": "select",
         "options": ["9:16", "16:9", "1:1", "4:5"]},
        {"name": "mode", "flag": "--mode", "label": "方式", "kind": "select", "options": ["pad", "crop"]}]},
    "subtitle": {"label": "燒錄字幕", "out": "mp4", "fields": [
        {"name": "srt", "flag": "--srt", "label": "SRT 檔（先上傳）", "kind": "file"},
        {"name": "size", "flag": "--size", "label": "字體大小", "kind": "number", "default": "24"}]},
    "bgm": {"label": "背景音樂", "out": "mp4", "fields": [
        {"name": "music", "flag": "--music", "label": "音樂檔（先上傳）", "kind": "file"},
        {"name": "volume", "flag": "--volume", "label": "音量 0~1", "kind": "number", "default": "0.3"}]},
    "extract-audio": {"label": "擷取音訊", "out": "mp3", "fields": []},
    "gif": {"label": "輸出 GIF", "out": "gif", "fields": [
        {"name": "start", "flag": "-s", "label": "開始", "kind": "text", "default": "0"},
        {"name": "duration", "flag": "-d", "label": "長度（秒）", "kind": "text", "default": "3"}]},
    "thumbnail": {"label": "封面圖", "out": "jpg", "fields": [
        {"name": "time", "flag": "-t", "label": "時間點", "kind": "text", "default": "0"}]},
    "silence": {"label": "移除靜音", "out": "mp4", "fields": [
        {"name": "noise", "flag": "--noise", "label": "靜音門檻 dB", "kind": "number", "default": "-30"},
        {"name": "min_silence", "flag": "--min-silence", "label": "最短靜音秒數", "kind": "number", "default": "0.5"}]},
}


def safe_name(name):
    name = os.path.basename(unquote(name))
    name = re.sub(r"[^\w.\-一-鿿]", "_", name).lstrip(".")
    return name or "file"


def in_work(name):
    path = os.path.join(WORK, safe_name(name))
    if not os.path.isfile(path):
        raise videocut.VideocutError(f"找不到檔案: {name}")
    return path


def list_files():
    out = []
    for n in sorted(os.listdir(WORK), key=lambda n: -os.path.getmtime(os.path.join(WORK, n))):
        p = os.path.join(WORK, n)
        if os.path.isfile(p):
            out.append({"name": n, "size": os.path.getsize(p)})
    return out


def run_job(req):
    cmd = req.get("cmd")
    spec = SPEC.get(cmd)
    if not spec:
        raise videocut.VideocutError("未知的功能")
    inputs = [in_work(n) for n in req.get("inputs", [])]
    if not inputs:
        raise videocut.VideocutError("請先選擇輸入影片")
    argv = [cmd] + (inputs if spec.get("multi") else inputs[:1])
    for f in spec["fields"]:
        v = req.get("params", {}).get(f["name"])
        if f["kind"] == "check":
            if v:
                argv.append(f["flag"])
        elif f["kind"] == "lines":
            for line in str(v or "").splitlines():
                if line.strip():
                    argv += [f["flag"], line.strip()]
        elif f["kind"] == "file":
            if not v and f.get("optional"):
                continue
            if not v:
                raise videocut.VideocutError(f"請選擇：{f['label']}")
            argv += [f["flag"], in_work(v)]
        elif v not in (None, ""):
            argv += [f["flag"], str(v)]
    out_name = None
    if spec["out"]:
        out_name = f"{cmd}_{uuid.uuid4().hex[:6]}.{spec['out']}"
        argv += ["-o", os.path.join(WORK, out_name)]
    buf = io.StringIO()
    try:
        args = videocut.build_parser().parse_args(argv)
    except SystemExit:
        raise videocut.VideocutError("參數有誤，請檢查欄位")
    with LOCK, contextlib.redirect_stdout(buf):
        args.fn(args)
    return {"output": out_name, "log": buf.getvalue().strip()}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False)
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            html = PAGE.replace("__SPEC__", json.dumps(SPEC, ensure_ascii=False))
            return self.send(200, html, "text/html; charset=utf-8")
        if u.path == "/api/files":
            return self.send(200, list_files())
        if u.path.startswith("/files/"):
            try:
                path = in_work(u.path[7:])
            except videocut.VideocutError:
                return self.send(404, {"error": "not found"})
            return self.serve_file(path, "download" in parse_qs(u.query))
        self.send(404, {"error": "not found"})

    def serve_file(self, path, download):
        import mimetypes
        size = os.path.getsize(path)
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        start, end, code = 0, size - 1, 200
        rng = self.headers.get("Range")
        if rng and (m := re.match(r"bytes=(\d*)-(\d*)", rng)):
            if m[1]:
                start = int(m[1])
                end = int(m[2]) if m[2] else size - 1
            elif m[2]:
                start = max(0, size - int(m[2]))
            end = min(end, size - 1)
            code = 206
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if code == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        if download:
            self.send_header("Content-Disposition",
                             f"attachment; filename*=UTF-8''{quote(os.path.basename(path))}")
        self.end_headers()
        with open(path, "rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(1 << 20, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    break
                left -= len(chunk)

    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        try:
            if u.path == "/api/upload":
                if n > MAX_UPLOAD:
                    return self.send(413, {"error": "檔案過大"})
                name = safe_name(parse_qs(u.query).get("name", ["file"])[0])
                with open(os.path.join(WORK, name), "wb") as f:
                    left = n
                    while left > 0:
                        chunk = self.rfile.read(min(1 << 20, left))
                        if not chunk:
                            break
                        f.write(chunk)
                        left -= len(chunk)
                return self.send(200, {"name": name})
            if u.path == "/api/run":
                return self.send(200, run_job(json.loads(self.rfile.read(n) or b"{}")))
            if u.path == "/api/delete":
                os.remove(in_work(json.loads(self.rfile.read(n))["name"]))
                return self.send(200, {"ok": True})
        except videocut.VideocutError as e:
            return self.send(400, {"error": str(e)})
        except Exception as e:  # noqa: BLE001
            return self.send(500, {"error": f"內部錯誤: {e}"})
        self.send(404, {"error": "not found"})


PAGE = r"""<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Videocut 剪片工具</title>
<style>
*{box-sizing:border-box}body{font-family:system-ui,"Noto Sans TC",sans-serif;margin:0;background:#f4f5f7;color:#222}
header{background:#1f2937;color:#fff;padding:14px 20px;font-size:18px}
main{display:grid;grid-template-columns:1fr 1fr;gap:16px;padding:16px;max-width:1100px;margin:auto}
@media(max-width:800px){main{grid-template-columns:1fr}}
section{background:#fff;border-radius:10px;padding:16px;box-shadow:0 1px 3px #0001}
h2{margin:0 0 12px;font-size:16px}
label{display:block;margin:10px 0 4px;font-size:13px;color:#555}
input[type=text],input[type=number],select,textarea{width:100%;padding:8px;border:1px solid #ccc;border-radius:6px;font-size:14px}
button{background:#2563eb;color:#fff;border:0;border-radius:6px;padding:9px 16px;font-size:14px;cursor:pointer}
button:disabled{background:#9ca3af}button.s{background:#e5e7eb;color:#333;padding:3px 8px;font-size:12px}
#drop{border:2px dashed #aaa;border-radius:8px;padding:18px;text-align:center;color:#666;cursor:pointer}
#drop.over{background:#eff6ff;border-color:#2563eb}
.file{display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid #eee;font-size:13px}
.file span.n{flex:1;word-break:break-all}.file a{color:#2563eb;font-size:12px}
#msg{margin-top:10px;font-size:13px;white-space:pre-wrap}.err{color:#b91c1c}.ok{color:#15803d}
video,img,audio{width:100%;margin-top:10px;border-radius:6px;background:#000}
</style></head><body>
<header>🎬 Videocut 剪片工具</header>
<main>
<section><h2>1. 上傳與選擇檔案</h2>
<div id="drop">點擊或拖曳檔案到這裡上傳</div><input id="pick" type="file" multiple hidden>
<div id="prog"></div><div id="files" style="margin-top:10px"></div></section>
<section><h2>2. 選擇功能</h2>
<select id="cmd"></select><div id="fields"></div>
<div style="margin-top:14px"><button id="run">執行</button></div>
<div id="msg"></div><div id="result"></div></section>
</main>
<script>
const SPEC=__SPEC__;const $=s=>document.querySelector(s);
const cmd=$('#cmd');for(const k in SPEC)cmd.add(new Option(SPEC[k].label+'  ('+k+')',k));
let files=[],sel=new Set();
function fmt(n){return n>1e6?(n/1e6).toFixed(1)+' MB':(n/1e3).toFixed(0)+' KB'}
async function load(){files=await (await fetch('/api/files')).json();draw();fields()}
function draw(){const el=$('#files');el.innerHTML=files.length?'':'<div style="color:#888;font-size:13px">尚無檔案</div>';
 for(const f of files){const d=document.createElement('div');d.className='file';
  const cb=document.createElement('input');cb.type='checkbox';cb.checked=sel.has(f.name);
  cb.onchange=()=>{cb.checked?sel.add(f.name):sel.delete(f.name)};
  d.append(cb);const n=document.createElement('span');n.className='n';n.textContent=f.name+' ('+fmt(f.size)+')';d.append(n);
  const a=document.createElement('a');a.href='/files/'+encodeURIComponent(f.name)+'?download';a.textContent='下載';d.append(a);
  const x=document.createElement('button');x.className='s';x.textContent='刪除';
  x.onclick=async()=>{await fetch('/api/delete',{method:'POST',body:JSON.stringify({name:f.name})});sel.delete(f.name);load()};d.append(x);el.append(d)}}
function fields(){const el=$('#fields');el.innerHTML='';const sp=SPEC[cmd.value];
 for(const f of sp.fields){const l=document.createElement('label');l.textContent=f.label;let i;
  if(f.kind=='select'){i=document.createElement('select');f.options.forEach(o=>i.add(new Option(o,o)))}
  else if(f.kind=='file'){i=document.createElement('select');if(f.optional)i.add(new Option('（不使用）',''));files.forEach(x=>i.add(new Option(x.name,x.name)))}
  else if(f.kind=='lines'){i=document.createElement('textarea');i.rows=4;i.placeholder='0-5\n12-20'}
  else if(f.kind=='check'){i=document.createElement('input');i.type='checkbox';l.prepend(i);i.dataset.n=f.name;el.append(l);continue}
  else{i=document.createElement('input');i.type=f.kind=='number'?'number':'text';i.step='any';if(f.default)i.value=f.default}
  i.dataset.n=f.name;el.append(l,i)}}
cmd.onchange=fields;
async function upload(list){for(const f of list){$('#prog').textContent='上傳中: '+f.name;
 const r=await fetch('/api/upload?name='+encodeURIComponent(f.name),{method:'POST',body:f});
 const j=await r.json();if(j.name)sel.add(j.name)}$('#prog').textContent='';load()}
const drop=$('#drop'),pick=$('#pick');drop.onclick=()=>pick.click();pick.onchange=()=>upload([...pick.files]);
drop.ondragover=e=>{e.preventDefault();drop.classList.add('over')};drop.ondragleave=()=>drop.classList.remove('over');
drop.ondrop=e=>{e.preventDefault();drop.classList.remove('over');upload([...e.dataTransfer.files])};
$('#run').onclick=async()=>{const m=$('#msg'),b=$('#run');m.className='';$('#result').innerHTML='';
 const inputs=files.filter(f=>sel.has(f.name)).map(f=>f.name);
 if(!inputs.length){m.className='err';m.textContent='請先勾選至少一個檔案';return}
 const params={};$('#fields').querySelectorAll('[data-n]').forEach(i=>params[i.dataset.n]=i.type=='checkbox'?i.checked:i.value);
 b.disabled=true;m.textContent='處理中…';
 try{const r=await fetch('/api/run',{method:'POST',body:JSON.stringify({cmd:cmd.value,inputs,params})});
  const j=await r.json();if(!r.ok){m.className='err';m.textContent=j.error;return}
  m.className='ok';m.textContent=j.log||'完成';
  if(j.output){const u='/files/'+encodeURIComponent(j.output);const e=j.output.split('.').pop();
   const tag=e=='jpg'||e=='gif'?'img':e=='mp3'?'audio':'video';const el=document.createElement(tag);el.src=u;if(tag!='img')el.controls=true;
   const a=document.createElement('a');a.href=u+'?download';a.textContent='下載 '+j.output;
   $('#result').append(el,document.createElement('br'),a);sel.clear();sel.add(j.output)}
  load()}catch(e){m.className='err';m.textContent=e}finally{b.disabled=false}};
load();
</script></body></html>
"""


def main():
    ap = argparse.ArgumentParser(description="videocut 網頁介面")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    os.makedirs(WORK, exist_ok=True)
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    print(f"Videocut 網頁介面: http://{a.host}:{a.port}  （Ctrl+C 結束）")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
