#!/usr/bin/env python3
"""videocut - 以 ffmpeg 為核心的命令列剪片工具。

用法範例:
  python videocut.py info in.mp4
  python videocut.py trim in.mp4 -s 00:00:05 -e 00:00:15 -o clip.mp4
  python videocut.py cut in.mp4 --keep 0-5 --keep 12-20 -o highlights.mp4
  python videocut.py concat a.mp4 b.mp4 c.mp4 -o all.mp4
  python videocut.py speed in.mp4 -f 2 -o fast.mp4
  python videocut.py resize in.mp4 --preset 9:16 -o vertical.mp4
  python videocut.py subtitle in.mp4 --srt subs.srt -o subbed.mp4
  python videocut.py bgm in.mp4 --music song.mp3 --volume 0.3 -o with_music.mp4
  python videocut.py extract-audio in.mp4 -o audio.mp3
  python videocut.py gif in.mp4 -s 3 -d 4 -o out.gif
  python videocut.py thumbnail in.mp4 -t 00:00:03 -o cover.jpg
  python videocut.py silence in.mp4 -o trimmed.mp4      # 自動移除靜音片段
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile


def die(msg):
    print(f"錯誤: {msg}", file=sys.stderr)
    sys.exit(1)


def run(cmd, capture=False):
    for exe in ("ffmpeg", "ffprobe"):
        if cmd[0] == exe and not shutil.which(exe):
            die(f"找不到 {exe}，請先安裝 ffmpeg")
    r = subprocess.run(cmd, capture_output=capture, text=True)
    if r.returncode != 0:
        die(f"指令失敗: {' '.join(cmd)}\n{(r.stderr or '')[-800:]}")
    return r


def ff(*args):
    return run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args])


def need(path):
    if not os.path.isfile(path):
        die(f"找不到檔案: {path}")
    return path


def probe(path):
    r = run(["ffprobe", "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", need(path)], capture=True)
    return json.loads(r.stdout)


def has_audio(path):
    return any(s["codec_type"] == "audio" for s in probe(path)["streams"])


def duration(path):
    return float(probe(path)["format"]["duration"])


def to_sec(t):
    """支援 90、1:30、00:01:30.5"""
    parts = str(t).split(":")
    try:
        sec = 0.0
        for p in parts:
            sec = sec * 60 + float(p)
        return sec
    except ValueError:
        die(f"時間格式錯誤: {t}")


# ---------- 指令 ----------

def cmd_info(a):
    d = probe(a.input)
    print(f"檔案: {a.input}")
    print(f"長度: {float(d['format']['duration']):.2f} 秒  大小: {int(d['format']['size'])/1e6:.1f} MB")
    for s in d["streams"]:
        if s["codec_type"] == "video":
            print(f"視訊: {s['codec_name']} {s['width']}x{s['height']} {s.get('r_frame_rate')} fps")
        elif s["codec_type"] == "audio":
            print(f"音訊: {s['codec_name']} {s.get('sample_rate')} Hz {s.get('channels')} ch")


def cmd_trim(a):
    args = ["-ss", str(to_sec(a.start))]
    if a.end:
        args += ["-to", str(to_sec(a.end))]
    args += ["-i", need(a.input)]
    args += ["-c", "copy"] if a.fast else ["-c:v", "libx264", "-c:a", "aac"]
    ff(*args, a.output)
    print(f"已輸出 {a.output}")


def cmd_cut(a):
    """保留多個區段並合併。--keep 起-迄，例如 0-5、00:10-00:20。"""
    need(a.input)
    segs = []
    for k in a.keep:
        m = re.fullmatch(r"(.+?)-(.+)", k)
        if not m:
            die(f"--keep 格式應為 起-迄: {k}")
        s, e = to_sec(m[1]), to_sec(m[2])
        if e <= s:
            die(f"區段迄點需大於起點: {k}")
        segs.append((s, e))
    audio = has_audio(a.input)
    parts, labels = [], ""
    for i, (s, e) in enumerate(segs):
        parts.append(f"[0:v]trim=start={s}:end={e},setpts=PTS-STARTPTS[v{i}]")
        labels += f"[v{i}]"
        if audio:
            parts.append(f"[0:a]atrim=start={s}:end={e},asetpts=PTS-STARTPTS[a{i}]")
            labels += f"[a{i}]"
    n = len(segs)
    parts.append(f"{labels}concat=n={n}:v=1:a={1 if audio else 0}[v]" + ("[a]" if audio else ""))
    maps = ["-map", "[v]"] + (["-map", "[a]"] if audio else [])
    ff("-i", a.input, "-filter_complex", ";".join(parts), *maps, a.output)
    print(f"已輸出 {a.output}（{n} 段）")


def cmd_concat(a):
    for f in a.inputs:
        need(f)
    # 先統一規格再合併，避免解析度/編碼不同導致失敗
    w, h = 1920, 1080
    first = next(s for s in probe(a.inputs[0])["streams"] if s["codec_type"] == "video")
    w, h = first["width"], first["height"]
    ins, parts, labels = [], [], ""
    for i, f in enumerate(a.inputs):
        ins += ["-i", f]
        parts.append(f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
                     f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v{i}]")
        if has_audio(f):
            parts.append(f"[{i}:a]aresample=44100,aformat=channel_layouts=stereo[a{i}]")
        else:
            parts.append(f"anullsrc=r=44100:cl=stereo,atrim=duration={duration(f)}[a{i}]")
        labels += f"[v{i}][a{i}]"
    parts.append(f"{labels}concat=n={len(a.inputs)}:v=1:a=1[v][a]")
    ff(*ins, "-filter_complex", ";".join(parts), "-map", "[v]", "-map", "[a]", a.output)
    print(f"已輸出 {a.output}")


def atempo_chain(f):
    chain = []
    while f > 2.0:
        chain.append("atempo=2.0"); f /= 2.0
    while f < 0.5:
        chain.append("atempo=0.5"); f /= 0.5
    chain.append(f"atempo={f:.4f}")
    return ",".join(chain)


def cmd_speed(a):
    if a.factor <= 0:
        die("倍率必須大於 0")
    args = ["-i", need(a.input), "-filter:v", f"setpts=PTS/{a.factor}"]
    if has_audio(a.input):
        args += ["-filter:a", atempo_chain(a.factor)]
    ff(*args, a.output)
    print(f"已輸出 {a.output}（{a.factor}x）")


PRESETS = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080), "4:5": (1080, 1350)}


def cmd_resize(a):
    if a.preset:
        w, h = PRESETS[a.preset]
    elif a.width and a.height:
        w, h = a.width, a.height
    else:
        die("請指定 --preset 或 --width/--height")
    if a.mode == "crop":
        vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
    else:
        vf = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
              f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black")
    ff("-i", need(a.input), "-vf", vf, "-c:a", "copy", a.output)
    print(f"已輸出 {a.output}（{w}x{h}，{a.mode}）")


def cmd_subtitle(a):
    need(a.input); need(a.srt)
    # 以暫存相對路徑避開濾鏡對特殊字元的跳脫問題
    with tempfile.TemporaryDirectory() as td:
        shutil.copy(a.srt, os.path.join(td, "s.srt"))
        style = f"FontSize={a.size},Outline=2,MarginV=30"
        if a.font:
            style += f",FontName={a.font}"
        src = os.path.abspath(a.input)
        out = os.path.abspath(a.output)
        r = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", src,
                            "-vf", f"subtitles=s.srt:force_style='{style}'",
                            "-c:a", "copy", out], cwd=td, capture_output=True, text=True)
        if r.returncode:
            die(r.stderr[-800:])
    print(f"已輸出 {a.output}")


def cmd_bgm(a):
    need(a.input); need(a.music)
    vol = a.volume
    if has_audio(a.input):
        fc = (f"[1:a]volume={vol}[m];[0:a][m]amix=inputs=2:duration=first:"
              f"dropout_transition=0[a]")
    else:
        fc = f"[1:a]volume={vol}[a]"
    ff("-i", a.input, "-stream_loop", "-1", "-i", a.music, "-filter_complex", fc,
       "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-shortest", a.output)
    print(f"已輸出 {a.output}")


def cmd_extract_audio(a):
    ff("-i", need(a.input), "-vn", a.output)
    print(f"已輸出 {a.output}")


def cmd_gif(a):
    vf = f"fps={a.fps},scale={a.width}:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"
    ff("-ss", str(to_sec(a.start)), "-t", str(to_sec(a.duration)), "-i", need(a.input),
       "-vf", vf, a.output)
    print(f"已輸出 {a.output}")


def cmd_thumbnail(a):
    ff("-ss", str(to_sec(a.time)), "-i", need(a.input), "-frames:v", "1", "-q:v", "2", a.output)
    print(f"已輸出 {a.output}")


def cmd_silence(a):
    """偵測靜音並移除，只保留有聲音的片段。"""
    need(a.input)
    if not has_audio(a.input):
        die("影片沒有音訊，無法偵測靜音")
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", a.input, "-af",
                        f"silencedetect=noise={a.noise}dB:d={a.min_silence}", "-f", "null", "-"],
                       capture_output=True, text=True)
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    total = duration(a.input)
    keep, pos = [], 0.0
    for i, s in enumerate(starts):
        if s - pos > 0.1:
            keep.append((pos, s))
        pos = ends[i] if i < len(ends) else total
    if total - pos > 0.1:
        keep.append((pos, total))
    if not keep:
        die("整支影片都被判定為靜音，請調整 --noise")
    print(f"偵測到 {len(starts)} 段靜音，保留 {len(keep)} 段")
    a.keep = [f"{s:.3f}-{e:.3f}" for s, e in keep]
    cmd_cut(a)


def build_parser():
    p = argparse.ArgumentParser(prog="videocut", description="ffmpeg 剪片工具",
                                formatter_class=argparse.RawDescriptionHelpFormatter,
                                epilog=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_, inp=True, out=True):
        sp = sub.add_parser(name, help=help_)
        if inp:
            sp.add_argument("input")
        if out:
            sp.add_argument("-o", "--output", required=True)
        sp.set_defaults(fn=fn)
        return sp

    add("info", cmd_info, "顯示影片資訊", out=False)
    sp = add("trim", cmd_trim, "裁切單一區段")
    sp.add_argument("-s", "--start", default="0")
    sp.add_argument("-e", "--end")
    sp.add_argument("--fast", action="store_true", help="不重新編碼（快，但切點可能不精準）")
    sp = add("cut", cmd_cut, "保留多個區段並合併")
    sp.add_argument("--keep", action="append", required=True, metavar="起-迄")
    sp = add("concat", cmd_concat, "合併多支影片", inp=False)
    sp.add_argument("inputs", nargs="+")
    sp = add("speed", cmd_speed, "變速")
    sp.add_argument("-f", "--factor", type=float, required=True)
    sp = add("resize", cmd_resize, "改比例/解析度")
    sp.add_argument("--preset", choices=PRESETS)
    sp.add_argument("--width", type=int)
    sp.add_argument("--height", type=int)
    sp.add_argument("--mode", choices=["pad", "crop"], default="pad")
    sp = add("subtitle", cmd_subtitle, "燒錄 SRT 字幕")
    sp.add_argument("--srt", required=True)
    sp.add_argument("--size", type=int, default=24)
    sp.add_argument("--font")
    sp = add("bgm", cmd_bgm, "加背景音樂")
    sp.add_argument("--music", required=True)
    sp.add_argument("--volume", type=float, default=0.3)
    add("extract-audio", cmd_extract_audio, "擷取音訊")
    sp = add("gif", cmd_gif, "輸出 GIF")
    sp.add_argument("-s", "--start", default="0")
    sp.add_argument("-d", "--duration", default="3")
    sp.add_argument("--fps", type=int, default=12)
    sp.add_argument("--width", type=int, default=480)
    sp = add("thumbnail", cmd_thumbnail, "擷取封面圖")
    sp.add_argument("-t", "--time", default="0")
    sp = add("silence", cmd_silence, "自動移除靜音片段")
    sp.add_argument("--noise", type=int, default=-30, help="靜音門檻 dB")
    sp.add_argument("--min-silence", type=float, default=0.5)
    return p


def main():
    a = build_parser().parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
