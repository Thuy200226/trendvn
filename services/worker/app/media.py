import base64
import json
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import wave
import textwrap
from pathlib import Path
from core import MODEL_FALLBACKS, TTS_FALLBACKS, file_hash, validate_analysis
from prompts import ANALYSIS_PROMPT, ANALYSIS_SCHEMA, PROMPT_VERSION, TTS_PROMPT

class RateLimited(ValueError):
    pass

class Transient(RateLimited):
    """Google is overloaded or throttling right now; the job goes back to the queue instead of being marked broken."""

class VoiceoverUnfit(ValueError):
    pass

TRANSIENT=(429,500,502,503,504)

def run(args, timeout=300):
    p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
    if p.returncode: raise ValueError('Media operation failed: '+p.stderr.decode(errors='replace')[-700:])
    return p.stdout

def probe(path):
    result=json.loads(run(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(path)]))
    duration=float(result['format']['duration'])
    if not any(s['codec_type']=='video' for s in result['streams']): raise ValueError('No video stream')
    return duration,result

def fingerprint(path,duration):
    hashes=[]
    for fraction in (0.15,0.35,0.55,0.75,0.90):
        frame=run(['ffmpeg','-v','error','-ss',str(duration*fraction),'-i',str(path),'-frames:v','1',
                   '-vf','scale=9:8,format=gray','-f','rawvideo','-'])
        if len(frame)!=72: raise ValueError('Cannot fingerprint frame')
        bits=[frame[y*9+x] > frame[y*9+x+1] for y in range(8) for x in range(8)]
        hashes.append(format(sum(int(b)<<i for i,b in enumerate(bits)),'016x'))
    return hashes

def similar(a,b):
    return len(a)==len(b)==5 and sum((int(x,16)^int(y,16)).bit_count()<=6 for x,y in zip(a,b))>=4

def gemini(store,model,body):
    key_file=store.root/'gemini.key'
    if not key_file.exists(): raise ValueError('Gemini API key is not configured')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+',model): raise ValueError('Invalid Gemini model')
    with store.transaction() as db:
        used=db.execute('SELECT count(*) FROM api_calls WHERE at>?',(time.time()-86400,)).fetchone()[0]
        limit=store.settings().get('gemini_daily_limit',12)
        if used>=limit: raise RateLimited('Local rolling 24-hour limit of %d Gemini calls reached'%limit)
        stamp=time.time()
        db.execute('INSERT INTO api_calls VALUES(?,?,?)',(stamp,model,'started'))
    request=urllib.request.Request('https://generativelanguage.googleapis.com/v1beta/models/'+model+':generateContent',
        data=json.dumps(body).encode(),headers={'Content-Type':'application/json','x-goog-api-key':key_file.read_text().strip()})
    try:
        with urllib.request.urlopen(request,timeout=100) as r: data=json.load(r)
    except urllib.error.HTTPError as e:
        if e.code in (400,401,403,404)+TRANSIENT:
            with store.transaction() as db:   # a rejected request was not processed, so it does not use up the daily allowance
                db.execute('DELETE FROM api_calls WHERE at=? AND model=?',(stamp,model))
        try:message=json.loads(e.read().decode()).get('error',{}).get('message','')[:220]   # Google's message never contains our key
        except Exception:message=''
        raise ValueError('Gemini HTTP %d (%s)%s'%(e.code,model,': '+message if message else '')) from None
    except Exception:
        # Timeout or dropped connection. Analysis and voice generation have no side effects, so this is retried like an overload;
        # the row is removed so retries cannot exhaust the local daily allowance.
        with store.transaction() as db:
            db.execute('DELETE FROM api_calls WHERE at=? AND model=?',(stamp,model))
        raise ValueError('Gemini HTTP 504 (%s): no response in time'%model) from None
    return data

def call_with_fallback(store,cfg,key,chain_default,fn,rounds=4,waits=(10,30,60),budget=240):
    """Run fn(model) with the configured model, then the fallback chain when Google says a model is gone (404) or overloaded (429/5xx).
    Overload is retried after a short wait; if it persists, Transient is raised so the job is re-queued, never marked broken.
    The first model that works is remembered so later calls go straight to it."""
    chain=[cfg[key]]+[m for m in chain_default if m!=cfg[key]]
    last=None;transient=False;deadline=time.time()+budget    # one call never holds the worker (and n8n's HTTP request) longer than the budget
    for rnd in range(rounds):
        transient=False
        for model in chain:
            if time.time()>deadline and last is not None:
                raise Transient('Gemini không phản hồi kịp (%ds), sẽ thử lại sau: %s'%(budget,last))
            try:
                result=fn(model)
            except ValueError as e:
                text=str(e)
                if 'HTTP 404' in text:last=e;continue
                if any('HTTP %d'%c in text for c in TRANSIENT):last=e;transient=True;continue
                raise
            if model!=cfg[key]:
                with store.transaction() as db:db.execute('UPDATE settings SET value=? WHERE key=?',(json.dumps(model),key))
                cfg[key]=model
            return result
        if not transient:break
        if rnd<rounds-1:time.sleep(min(waits[rnd],max(0,deadline-time.time())))
    if transient:raise Transient('Gemini đang quá tải, sẽ thử lại sau: '+str(last))
    raise last

def generate(store,cfg,parts,schema=None):
    """One structured Gemini call. If the API rejects the schema (HTTP 400) retry once without it; the strict local validator still applies."""
    gen={'responseMimeType':'application/json','temperature':0.1}
    if schema:gen['responseSchema']=schema
    body={'contents':[{'parts':parts}],'generationConfig':gen}
    def attempt(model):
        try:return gemini(store,model,body)
        except ValueError as e:
            if gen.get('responseSchema') and 'HTTP 400' in str(e):
                gen.pop('responseSchema');return gemini(store,model,body)
            raise
    return call_with_fallback(store,cfg,'model',MODEL_FALLBACKS,attempt)

def analyze(store,path,duration,cfg,folder,lenient=False):
    proxy=folder/'analysis.mp4'
    run(['ffmpeg','-v','error','-y','-i',str(path),'-vf','scale=384:-2,fps=2','-c:v','libx264','-preset','fast',
         '-crf','32','-c:a','aac','-b:a','48k','-movflags','+faststart',str(proxy)])
    if proxy.stat().st_size>12*1024*1024: raise ValueError('Analysis proxy exceeds 12MB')
    parts=[{'text':ANALYSIS_PROMPT+'\nVideo length: %.1f seconds.'%duration},
           {'inline_data':{'mime_type':'video/mp4','data':base64.b64encode(proxy.read_bytes()).decode()}}]
    data=generate(store,cfg,parts,ANALYSIS_SCHEMA)
    parts=data.get('candidates',[{}])[0].get('content',{}).get('parts',[])
    text=''.join(p.get('text','') for p in parts)
    try:a=json.loads(text)
    except Exception:raise ValueError('Gemini did not return valid analysis JSON') from None
    if isinstance(a,list) and a:a=a[0]
    route=validate_analysis(a,duration,cfg['audio_confidence'],strict=True,lenient=lenient)
    return a,route

def timestamp(t):
    ms=round(t*1000); seconds,ms=divmod(ms,1000); minutes,seconds=divmod(seconds,60); hours,minutes=divmod(minutes,60)
    return f'{hours:02}:{minutes:02}:{seconds:02},{ms:03}'

def subtitles(segments,path):
    lines=[]
    for i,s in enumerate(segments,1):
        text=re.sub(r'<[^>]*>','',s['vi']).replace('\r',' ').replace('\n',' ').replace('-->','→').replace('{','(').replace('}',')')
        lines.append(f"{i}\n{timestamp(s['start'])} --> {timestamp(s['end'])}\n{text.strip()}\n")
    path.write_text('\n'.join(lines),encoding='utf-8')

def ass_subtitles(segments,path,width,height,band_top=None,zone=None):
    """zone (from caption_zone) says where captions go; band_top is the older shortcut for a free band below the picture."""
    def ass_time(t):
        cs=round(t*100);secs,cs=divmod(cs,100);mins,secs=divmod(secs,60);hours,mins=divmod(mins,60)
        return f'{hours}:{mins:02}:{secs:02}.{cs:02}'
    font=max(14,round(width*0.047))
    left=max(12,round(width*.045));right=max(30,round(width*.12))
    margin=max(30,round(height*.18))
    if zone is None and band_top is not None:zone={'align':8,'margin':band_top+round(height*.025),'box':False}
    if zone is None:zone={'align':2,'margin':round(height*.27),'box':True}
    align,margin=zone['align'],zone['margin']
    border,outline=(3,max(4,round(font*.28))) if zone['box'] else (1,max(3,round(font*.09)))   # a box over the picture, plain outline on the blurred band
    chars=max(20,int((width-left-right)/(font*.52)))
    header=f'''[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,{font},&H00FFFFFF,&H000000FF,&H30000000,&H30000000,-1,0,0,0,100,100,0,0,{border},{outline},0,{align},{left},{right},{margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    events=[]
    for s in segments:
        txt=re.sub(r'<[^>]*>','',s['vi']).replace('\\','＼').replace('{','(').replace('}',')')
        txt=' '.join(txt.split())
        lines=textwrap.wrap(txt,width=chars,break_long_words=True,break_on_hyphens=False)
        # Long sentences become consecutive two-line captions sharing the segment's time in proportion to their text.
        chunks=[lines[i:i+2] for i in range(0,len(lines),2)]
        weights=[sum(len(x) for x in c) for c in chunks]
        start=s['start'];span=s['end']-s['start']
        for c,w in zip(chunks,weights):
            end=start+span*w/sum(weights)
            text='\\N'.join(c)
            events.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Default,,0,0,0,,{text}")
            start=end
    path.write_text(header+'\n'.join(events)+'\n',encoding='utf-8')

def tts(store,cfg,text,out):
    if not isinstance(text,str) or not text.strip() or len(text)>6000: raise ValueError('Invalid Vietnamese narration')
    body={'contents':[{'parts':[{'text':TTS_PROMPT+text}]}],
          'generationConfig':{'responseModalities':['AUDIO'],'speechConfig':{'voiceConfig':{'prebuiltVoiceConfig':{'voiceName':cfg['voice']}}}}}
    data=call_with_fallback(store,cfg,'tts_model',TTS_FALLBACKS,lambda m:gemini(store,m,body))
    parts=data.get('candidates',[{}])[0].get('content',{}).get('parts',[])
    audios=[p.get('inlineData',p.get('inline_data')) for p in parts if p.get('inlineData') or p.get('inline_data')]
    if not audios:raise ValueError('TTS did not return audio')
    audio=audios[0]; mime=audio.get('mimeType',audio.get('mime_type',''))
    raw=base64.b64decode(audio['data'],validate=True)
    if 'audio/L16' in mime or 'audio/pcm' in mime:
        rate_match=re.search(r'rate=(\d+)',mime); rate=int(rate_match.group(1)) if rate_match else 24000
        with wave.open(str(out),'wb') as w:
            w.setnchannels(1);w.setsampwidth(2);w.setframerate(rate);w.writeframes(raw)
    elif raw[:4]==b'RIFF' and raw[8:12]==b'WAVE':
        Path(out).write_bytes(raw)                                   # newer TTS models return a complete WAV file
    elif mime.startswith('audio/'):
        src=Path(str(out)+'.src');src.write_bytes(raw)               # mp3, ogg, ...: let ffmpeg normalise it to WAV
        try:run(['ffmpeg','-v','error','-y','-i',str(src),'-ar','24000','-ac','1',str(out)])
        finally:src.unlink(missing_ok=True)
    else:raise ValueError('Unexpected TTS audio format: '+mime[:40])
    with wave.open(str(out),'rb') as w:return w.getnframes()/w.getframerate()

def make_voice(store,cfg,a,folder):
    """Vietnamese narration audio fitted to the time window the original speech occupies."""
    text=(a.get('narration_vi') or '').strip() or ' '.join(s['vi'] for s in a['segments'])
    wav=folder/'voice.wav'
    seconds=tts(store,cfg,text,wav)
    start=a['segments'][0]['start'];end=a['segments'][-1]['end']
    span=max(2.0,end-start)
    ratio=seconds/span
    if not 0.7<=ratio<=1.4:raise VoiceoverUnfit('Giọng đọc %.1fs không khớp cửa sổ lời %.1fs'%(seconds,span))
    return {'wav':wav,'tempo':min(1.4,max(0.85,ratio)),'delay':start}

CANVAS=(1080,1920)

def display_size(stream):
    """Size the viewer sees: phones often store portrait video as landscape pixels plus a 90-degree rotation flag."""
    w,h=stream['width'],stream['height'];rot=0
    try:rot=int(float((stream.get('tags') or {}).get('rotate',0)))
    except (TypeError,ValueError):pass
    for sd in stream.get('side_data_list') or []:
        if isinstance(sd,dict) and 'rotation' in sd:
            try:rot=int(float(sd['rotation']))
            except (TypeError,ValueError):pass
    return (h,w) if abs(rot)%180==90 else (w,h)

def layout(width,height):
    """Output geometry. Portrait videos keep their pixels (capped at 1080x1920); wide or square ones go on a 1080x1920 canvas over a
    blurred copy of themselves, which is how they fill a phone screen instead of shrinking into a thin strip."""
    if width/height<=0.7:
        k=min(1.0,CANVAS[0]/width,CANVAS[1]/height)
        return {'reframe':False,'w':max(2,int(width*k)//2*2),'h':max(2,int(height*k)//2*2)}
    fg_h=round(CANVAS[0]*height/width/2)*2
    return {'reframe':True,'w':CANVAS[0],'h':CANVAS[1],'fg_h':fg_h,'band_top':(CANVAS[1]+fg_h)//2}

def caption_zone(geo):
    """Where Vietnamese captions go. TikTok draws the account name, caption and hashtags over roughly the lowest quarter of the screen
    (y above about 1450 of 1920 stays clear) and its tabs over the top ~130px, so captions sit in the free blurred band when there is
    one, otherwise above the lower overlay."""
    H=geo['h']
    if not geo['reframe']:return {'align':2,'margin':round(H*.27),'box':True}
    top_h=(H-geo['fg_h'])//2
    if geo['band_top']<=1340:return {'align':8,'margin':geo['band_top']+round(H*.025),'box':False}     # wide video: band below the picture
    if top_h>=260:return {'align':8,'margin':max(140,top_h//2-60),'box':False}                        # square or 4:5: band above the picture
    return {'align':8,'margin':top_h+30,'box':True}                                                   # 3:4: top of the picture

def fps_of(stream):
    try:
        n,d=stream.get('avg_frame_rate','0/1').split('/');return float(n)/float(d) if float(d) else 0
    except Exception:return 0

def render(path,folder,a,route,duration,voice=None):
    """One ffmpeg pass: reframe to 9:16, burn Vietnamese subtitles when the route needs them, mix the voice-over, level the sound,
    drop the source's metadata, and write a web-friendly MP4 (H.264 high, yuv420p, AAC, faststart)."""
    out=folder/'final.mp4'
    _,meta=probe(path)
    vs=next(s for s in meta['streams'] if s['codec_type']=='video')
    has_audio=any(s['codec_type']=='audio' for s in meta['streams'])
    geo=layout(*display_size(vs))
    chain=[]
    if geo['reframe']:
        chain.append('[0:v]split=2[bgs][fgs];[bgs]scale=108:192:force_original_aspect_ratio=increase,crop=108:192,boxblur=8:2,scale=%d:%d:flags=bilinear,eq=brightness=-0.08[bg];'
                     '[fgs]scale=%d:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2[v0]'%(geo['w'],geo['h'],geo['w']))   # blur a tiny copy, then enlarge: same look, ~4x faster
    else:
        chain.append('[0:v]scale=%d:%d[v0]'%(geo['w'],geo['h']))
    last='v0'
    if route!='original':
        subtitles(a['segments'],folder/'vi.srt')
        ass=folder/'vi.ass';ass_subtitles(a['segments'],ass,geo['w'],geo['h'],zone=caption_zone(geo))
        chain.append('[%s]ass=%s[v1]'%(last,ass));last='v1'     # folder is a generated UUID path, never user-controlled filter text
    if fps_of(vs)>30.5:
        chain.append('[%s]fps=30[v2]'%last);last='v2'
    chain.append('[%s]null[v]'%last)
    inputs=['-i',str(path)]
    if voice:
        inputs+=['-i',str(voice['wav'])]
        delay=int(voice['delay']*1000)
        chain.append('[1:a]atempo=%.3f,adelay=%d|%d[vo]'%(voice['tempo'],delay,delay))
        if has_audio:
            chain.append('[0:a]volume=0.18[bg_a];[bg_a][vo]amix=inputs=2:duration=first:normalize=0[mix]');src='mix'
        else:src='vo'
        chain.append('[%s]loudnorm=I=-14:TP=-1.0:LRA=13,aresample=44100[a]'%src)
        amap=['-map','[a]']
    elif has_audio:
        chain.append('[0:a]loudnorm=I=-14:TP=-1.0:LRA=13,aresample=44100[a]')
        amap=['-map','[a]']
    else:amap=[]
    run(['ffmpeg','-v','error','-y',*inputs,'-filter_complex',';'.join(chain),'-map','[v]',*amap,'-t','%.3f'%duration,
         '-c:v','libx264','-preset','fast','-crf','23','-profile:v','high','-pix_fmt','yuv420p','-maxrate','4M','-bufsize','8M',
         '-c:a','aac','-b:a','160k','-ac','2','-map_metadata','-1','-movflags','+faststart',str(out)],timeout=900)
    final_duration,final_meta=probe(out)
    if abs(final_duration-duration)>1: raise ValueError('Rendered duration mismatch')
    run(['ffmpeg','-v','error','-i',str(out),'-f','null','-'])
    return out

def qc(out,source_has_audio):
    """Quality report of the rendered file: facts for the dashboard plus blocking problems. Returns (info, problems)."""
    duration,meta=probe(out)
    v=next(s for s in meta['streams'] if s['codec_type']=='video')
    audio=[s for s in meta['streams'] if s['codec_type']=='audio']
    info={'w':v['width'],'h':v['height'],'duration':round(duration,1),'size':int(meta['format'].get('size',0)),'codec':v.get('codec_name'),
          'pix_fmt':v.get('pix_fmt'),'audio':bool(audio),'portrait':v['height']>v['width'],'fps':round(fps_of(v))}
    problems=[]
    if v.get('codec_name')!='h264' or v.get('pix_fmt')!='yuv420p':problems.append('Định dạng video không phải H.264 yuv420p')
    if v['width']%2 or v['height']%2:problems.append('Kích thước hình lẻ')
    if source_has_audio and not audio:problems.append('Video gốc có tiếng nhưng bản dựng mất tiếng')
    if info['size']<20_000:problems.append('File dựng nhỏ bất thường')
    if min(v['width'],v['height'])<480:info['warning']='Độ phân giải thấp (%dx%d)'%(v['width'],v['height'])
    return info,problems

def make_poster(video,out,duration):
    """Small still for the dashboard so phones do not download the whole video just to show a card."""
    run(['ffmpeg','-v','error','-y','-ss','%.2f'%min(1.5,max(0.0,duration/3)),'-i',str(video),'-frames:v','1','-vf','scale=360:-2','-q:v','4',str(out)])

def process_one(store):
    cfg=store.settings()
    if not cfg['processing_enabled']:return {'status':'disabled','reason':'Enable processing after configuring Gemini'}
    if not (store.root/'gemini.key').exists():return {'status':'blocked','reason':'Gemini API key missing'}
    job=store.claim()
    if not job:return {'status':'idle','reason':'No staged media in queue'}
    jid,lease=job['id'],job['lease']
    folder=store.root/'jobs'/jid
    try:
        folder.mkdir(exist_ok=True)
        path=Path(job['source_file'])
        if file_hash(path)!=job['content_hash']:raise ValueError('Source file changed after attachment')
        duration,_=probe(path)
        if not 1<=duration<=cfg['max_duration']:raise ValueError('Video duration outside configured limits')
        fp=fingerprint(path,duration)
        with store.connect() as db:
            others=db.execute('SELECT id,fingerprint,duration FROM jobs WHERE fingerprint IS NOT NULL AND id<>?',(jid,)).fetchall()
        for row in ([] if job.get('approved') else others):         # the owner's approval overrides the look-alike warning
            if abs(row['duration']-duration)<2 and similar(fp,json.loads(row['fingerprint'])):
                store.finish(jid,lease,'needs_review',reason='Possible visual duplicate of '+row['id'],fingerprint=json.dumps(fp),duration=duration)
                return {'id':jid,'status':'needs_review'}
        a,route=analyze(store,path,duration,cfg,folder,lenient=bool(job.get('approved')))
        if not job.get('approved') and not str(a.get('caption_vi') or '').strip():
            raise ValueError('Gemini không soạn được mô tả tiếng Việt; cần bạn xem lại')
        voice=None;note=''
        if route=='voiceover':
            route='vietsub'
            if cfg['voiceover_enabled']:
                try:voice=make_voice(store,cfg,a,folder);route='voiceover'
                except Exception as e:note=' (lồng tiếng bỏ qua: %s)'%str(e)[:120]   # subtitles alone are a complete, safe result
        out=render(path,folder,a,route,duration,voice)
        _,src_meta=probe(path)
        info,problems=qc(out,any(s['codec_type']=='audio' for s in src_meta['streams']))
        if problems:raise ValueError('Kiểm tra chất lượng video dựng: '+'; '.join(problems))
        info['route']=route;info['reframed']=layout(*display_size(next(s for s in src_meta['streams'] if s['codec_type']=='video')))['reframe']
        try:make_poster(out,folder/'poster.jpg',duration);info['poster']=True
        except Exception:info['poster']=False
        digest=file_hash(out)
        (folder/'manifest.json').write_text(json.dumps({'id':jid,'source_url':job['url'],'source_hash':job['content_hash'],
            'output_hash':digest,'route':route,'target':cfg['target'],'analysis':a,'prompt_version':PROMPT_VERSION,'output_info':info,'published':False},ensure_ascii=False,indent=2))
        approval=cfg['require_approval'] and not job.get('approved')
        store.finish(jid,lease,'awaiting_approval' if approval else 'ready',analysis=json.dumps(a,ensure_ascii=False),route=route,output_file=str(out),
                     output_hash=digest,fingerprint=json.dumps(fp),duration=duration,output_info=json.dumps(info),
                     reason=('Đã dựng, chờ bạn duyệt' if approval else 'Đã dựng, sẵn sàng đăng')+note)
        return {'id':jid,'status':'awaiting_approval' if approval else 'ready','route':route}
    except RateLimited as e:
        store.release(jid,lease,str(e))
        return {'id':jid,'status':'rate_limited','reason':str(e)}
    except Exception as e:
        store.finish(jid,lease,'needs_review',reason=str(e)[:700])
        return {'id':jid,'status':'needs_review','reason':str(e)[:700]}
