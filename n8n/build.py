"""Build the n8n workflows of TrendVN from code (the source of truth is THIS file, not the JSON files).

    python3 n8n/build.py            write n8n/workflows/*.json for this machine (reads .env: agent port, timezone)
    python3 n8n/build.py --check    exit 1 if the committed JSON differs from what this file generates (defaults, ignores .env)

The JSON contains no secret: the worker token lives in an n8n credential that `./trendvn n8n import` creates from .env.
Node ids are derived from names, so rebuilding gives byte-identical files (clean diffs, safe re-import).
"""
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'n8n' / 'workflows'
CRED = {'httpHeaderAuth': {'id': 'trendvnWorkerAuth', 'name': 'TrendVN · Worker riêng'}}
WORKER = 'http://worker:8080'          # container-to-container address inside the project network
CHECK = '--check' in sys.argv[1:]
_NS = uuid.UUID('6f0c2a1e-7d3b-4c55-9a0e-2b7c1d4e5f60')


def _env():
    sys.path.insert(0, str(ROOT / 'scripts'))
    from envfile import parse
    return {} if CHECK else parse(ROOT / '.env')


ENV = _env()
AGENT = 'http://trendvn-agent:%s' % ENV.get('TRENDVN_AGENT_PORT', '5682')      # host agent, reachable only from this project's containers
TZ = ENV.get('TRENDVN_TZ', 'Asia/Ho_Chi_Minh')
DASH = 'http://localhost:%s' % ENV.get('TRENDVN_WORKER_PORT', '5681')
WRITTEN = {}
def node(name,kind,params,x,y=0,version=1,**extra):
    return {'id':uuid.uuid5(_NS,kind+'|'+name).hex,'name':name,'type':'n8n-nodes-base.'+kind,'typeVersion':version,'position':[x,y],'parameters':params,**extra}
def request(name,path,x,method='POST',base=WORKER,body='{}',y=0,tolerant=False,timeout=900000):
    params={'url':base+path,'method':method,'authentication':'genericCredentialType',
            'genericAuthType':'httpHeaderAuth','options':{'timeout':timeout}}
    if method=='POST':params.update({'sendBody':True,'specifyBody':'json','jsonBody':body})
    extra={'onError':'continueRegularOutput'} if tolerant else {}
    return node(name,'httpRequest',params,x,y,version=4.2,credentials=CRED,**extra)
def save(wid,name,nodes,edges):
    con={}
    for a,b in edges:con.setdefault(a,{'main':[[]]})['main'][0].append({'node':b,'type':'main','index':0})
    workflow={'id':wid,'name':name,'nodes':nodes,'connections':con,'active':False,
              'settings':{'executionOrder':'v1','timezone':TZ,'saveDataErrorExecution':'all',
                          'saveDataSuccessExecution':'all','saveManualExecutions':True},'pinData':{}}
    WRITTEN[wid+'.json']=json.dumps(workflow,ensure_ascii=False,indent=2)+'\n'
def chain(nodes):return [(a['name'],b['name']) for a,b in zip(nodes,nodes[1:]) if a['type']!='n8n-nodes-base.stickyNote' and b['type']!='n8n-nodes-base.stickyNote']

# 00 · readiness check (worker + host agent)
manual=node('Chạy kiểm tra','manualTrigger',{},0)
status=request('Đọc trạng thái worker','/api/status',260,'GET')
agent=node('Kiểm tra agent trình duyệt','httpRequest',{'url':AGENT+'/health','method':'GET','options':{'timeout':15000}},520,version=4.2,onError='continueRegularOutput')
code=node('Tổng hợp phần còn thiếu','code',{'jsCode':'''const s=$('Đọc trạng thái worker').first().json;
const a=$input.first().json;
const missing=[];
if(!a.ok) missing.push('Agent trình duyệt trên máy chưa chạy (systemd: trendvn-agent)');
if(!s.gemini_configured) missing.push('Chưa có khóa Gemini API');
if(!s.processing_enabled) missing.push('Xử lý video đang tắt');
if(s.discovery!=='connected') missing.push('Bộ thu thập chưa có lần chạy thành công');
if(s.publisher!=='connected') missing.push('Chưa đăng nhập TikTok trong hồ sơ riêng của trình đăng');
if(!s.publisher_enabled) missing.push('Công tắc Tự đăng đang tắt (chỉ bạn bật trên bảng điều khiển)');
if(s.unresolved_publishes>0) missing.push('Có bài chưa xác nhận đã đăng hay chưa');
return [{json:{...s,agent_ok:!!a.ok,ready_for_unattended_publishing:missing.length===0,missing}}];'''},780,version=2)
note=node('Ghi chú','stickyNote',{'content':'## Kiểm tra mức sẵn sàng\nĐọc trạng thái thật từ worker và agent. Không đổi dữ liệu.\nBảng điều khiển: '+DASH,'height':200,'width':520},100,-300)
save('trendvn00status','TrendVN | 00 · Kiểm tra kết nối và mức sẵn sàng',[manual,status,agent,code,note],chain([manual,status,agent,code]))

# 01 · collect + process (every 3 hours)
schedule=node('Mỗi 3 giờ','scheduleTrigger',{'rule':{'interval':[{'field':'hours','hoursInterval':3}]}},0,200,version=1.2)
manual=node('Chạy thử toàn chu trình','manualTrigger',{},0,0)
session=request('Kiểm tra phiên TikTok','/api/session',260,base=AGENT,tolerant=True,timeout=180000)
verify=request('Đối chiếu bài chưa xác nhận','/api/verify',520,base=AGENT,tolerant=True,timeout=300000)
collect=request('Thu thập xu hướng và tải video mới','/api/collect',780,base=AGENT,tolerant=True)
house=request('Phát hiện tác vụ gián đoạn','/api/housekeeping',1040,tolerant=True)
process=request('Phân loại nhạc, tạo Vietsub hoặc lồng tiếng','/api/process',1300,body='{"max":4}',tolerant=True)
note=node('Thu thập và xử lý','stickyNote',{'content':'## Chu trình 3 giờ/lần\n1. Kiểm tra phiên TikTok, đối chiếu bài chưa rõ kết quả\n2. Thu thập Douyin, Kuaishou, TikTok Mỹ, Instagram Mỹ; chỉ tải video MỚI, ưu tiên theo điểm thịnh hành\n3. Nhạc giữ nguyên; hội thoại thêm Vietsub; thuyết minh có thể lồng tiếng Việt\n4. Lệch chủ đề hoặc nhạy cảm bị giữ lại chờ bạn duyệt (có thông báo)\nViệc đăng nằm ở workflow 02 để canh đúng giờ vàng.','height':300,'width':760},260,-360)
first=[session,verify,collect,house,process]
save('trendvn01daily','TrendVN | 01 · Thu thập và xử lý (3 giờ/lần)',[schedule,manual]+first+[note],[(schedule['name'],session['name']),(manual['name'],session['name'])]+chain(first))

# 02 · publish in golden hours (every 30 minutes; the worker enforces switch, window, daily limit, spacing)
sched=node('Mỗi 30 phút','scheduleTrigger',{'rule':{'interval':[{'field':'minutes','minutesInterval':30}]}},0,200,version=1.2)
manual=node('Chạy thử đăng','manualTrigger',{},0,0)
publish=request('Đăng video tốt nhất nếu đủ điều kiện','/api/publish',300,base=AGENT,tolerant=True,timeout=1500000)
note=node('Đăng theo giờ vàng','stickyNote',{'content':'## Đăng bài\nMỗi 30 phút hỏi worker có được đăng không. Worker chỉ cho phép khi: công tắc Tự đăng bật, đang trong giờ vàng, chưa quá số bài mỗi ngày, đủ giãn cách, không có bài chưa xác nhận.\nKhông đủ điều kiện thì trả lời ngay, không mở trình duyệt.','height':240,'width':560},100,-300)
save('trendvn02publish','TrendVN | 02 · Đăng theo giờ vàng (30 phút/lần)',[sched,manual,publish,note],[(sched['name'],publish['name']),(manual['name'],publish['name'])])

# 03 · end of day: performance feedback + summary notification
cron=node('23:30 mỗi ngày','scheduleTrigger',{'rule':{'interval':[{'field':'cronExpression','expression':'30 23 * * *'}]}},0,200,version=1.2)
manual=node('Chạy thử chốt ngày','manualTrigger',{},0,0)
stats=request('Đọc lượt xem các bài đã đăng','/api/stats',300,base=AGENT,tolerant=True,timeout=300000)
summary=request('Gửi tóm tắt ngày','/api/notify',560,body='{"kind":"summary"}',tolerant=True)
note=node('Chốt ngày','stickyNote',{'content':'## Chốt ngày\nĐọc lượt xem, tim của bài đã đăng để hệ thống tự điều chỉnh độ ưu tiên từng nguồn (cần tối thiểu 8 bài), rồi gửi tóm tắt qua kênh thông báo bạn đã cấu hình.','height':220,'width':560},100,-280)
save('trendvn03daily','TrendVN | 03 · Chốt ngày: hiệu quả và tóm tắt',[cron,manual,stats,summary,note],[(cron['name'],stats['name']),(manual['name'],stats['name']),(stats['name'],summary['name'])])

# 10 · authenticated observation intake (unchanged contract)
webhook=node('Nhận quan sát nguồn','webhook',{'httpMethod':'POST','path':'trendvn-observations','authentication':'headerAuth','responseMode':'lastNode','options':{}},0,version=2,credentials=CRED,webhookId='trendvn-observations')
ingest=request('Lưu mốc và nhận diện video mới','/api/ingest',280)
ingest['parameters']['jsonBody']='={{ JSON.stringify($json.body) }}'
note=node('Hợp đồng dữ liệu','stickyNote',{'content':'## Đầu vào JSON có xác thực (nhập tay hoặc công cụ khác)\nplatform, stream, observed_at (Unix seconds), items[]\nMỗi item: source_id, url HTTPS chính chủ, country CN/US, title, rank hoặc views, evidence_url.\nLần đầu chỉ tạo baseline. Bộ thu thập tự động dùng workflow 01, không cần webhook này.','height':230,'width':560},0,-300)
save('trendvn10inbox','TrendVN | 10 · Nhận quan sát và chống trùng ID',[webhook,ingest,note],[(webhook['name'],ingest['name'])])

# 20 · manual processing run
manual=node('Chạy xử lý thử','manualTrigger',{},0)
house=request('Phát hiện tác vụ gián đoạn','/api/housekeeping',260)
process=request('Phân loại nhạc và tạo Vietsub','/api/process',520,body='{"max":4}')
note=node('Xử lý thủ công','stickyNote',{'content':'## Chạy tay bước xử lý\nNhạc: giữ nguyên âm thanh. Hội thoại/thuyết minh: Vietsub.\nKiểm tra hash nguồn, dấu vân tay hình ảnh, thời lượng, chủ đề, nhạy cảm và giải mã đầu ra.\nLịch tự động nằm ở workflow 01 (thu thập, xử lý) và 02 (đăng).','height':240,'width':560},150,-300)
save('trendvn20process','TrendVN | 20 · Xử lý video và phụ đề Việt',[manual,house,process,note],chain([manual,house,process]))

if CHECK:
    stale=[n for n,text in WRITTEN.items() if not (OUT/n).exists() or (OUT/n).read_text()!=text]
    extra=[f.name for f in OUT.glob('*.json') if f.name not in WRITTEN]
    if stale or extra:
        print('n8n/workflows không khớp n8n/build.py: %s. Chạy ./trendvn n8n build.' % ', '.join(stale+extra)); sys.exit(1)
    print('OK: %d workflow khớp mã sinh.' % len(WRITTEN))
else:
    OUT.mkdir(parents=True,exist_ok=True)
    for name,text in WRITTEN.items():(OUT/name).write_text(text)
    print('Đã sinh %d workflow (chưa bật, không chứa bí mật): %s' % (len(WRITTEN),OUT.relative_to(ROOT)))
