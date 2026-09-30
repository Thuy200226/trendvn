"""Offline media integration test. Synthetic fixtures only; no uploads or AI calls."""
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0,'/app')
from media import run,probe,fingerprint,render,similar

root=Path('/tmp/trendvn-render-check');root.mkdir(exist_ok=True)
source=root/'synthetic.mp4'
run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=size=360x640:rate=25',
     '-f','lavfi','-i','sine=frequency=440:sample_rate=44100','-t','6',
     '-vf',"drawtext=text='TEST ONLY - NOT A REAL TREND':fontcolor=white:fontsize=16:x=15:y=80",
     '-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(source)])
duration,_=probe(source)
assert abs(duration-6)<0.2
fp=fingerprint(source,duration)
analysis={'kind':'dialogue','confidence':0.99,'segments':[
    {'start':0.5,'end':2.5,'vi':'Đây là video kiểm thử phụ đề tiếng Việt.'},
    {'start':3,'end':5.5,'vi':'Không phải video thịnh hành hoặc bài đăng thật.'}]}
subdir=root/'subtitles';subdir.mkdir(exist_ok=True)
out=render(source,subdir,analysis,'vietsub',duration)
assert out.stat().st_size>1000
passthrough=root/'music';passthrough.mkdir(exist_ok=True)
music=render(source,passthrough,{'segments':[]},'original',duration)
assert similar(fp,fingerprint(music,duration))
run(['ffmpeg','-v','error','-y','-ss','1.5','-i',str(out),'-frames:v','1',str(root/'preview.png')])
print(json.dumps({'media_decode':'passed','duration':'passed','subtitle_render':'passed','original_audio_route':'passed',
                  'fingerprint':'passed','fixture':'synthetic only','gemini_live':'not tested','tiktok_publish':'not tested'}))
