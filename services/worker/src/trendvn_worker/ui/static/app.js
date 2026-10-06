(function(){
  var phone=window.matchMedia('(max-width:720px)'),tabs=['home','search','queue','publish','attention','posted','more'];
  function tabOf(hash){
    var h=(hash||'').replace('#','');
    if(tabs.indexOf(h)>=0)return {tab:h};
    var el=h&&document.getElementById(h);
    if(el){var s=el.closest('section[data-tab]');if(s)return {tab:s.dataset.tab,open:el};}
    return {tab:'home'};
  }
  function apply(){
    document.body.classList.toggle('tabs',phone.matches);
    var r=tabOf(location.hash),cur=r.tab;
    document.querySelectorAll('section[data-tab]').forEach(function(s){s.classList.toggle('on',s.dataset.tab===cur);});
    document.querySelectorAll('[data-go]').forEach(function(a){a.classList.toggle('on',a.dataset.go===cur);});
    if(r.open&&r.open.tagName==='DETAILS'){r.open.open=true;if(phone.matches)setTimeout(function(){r.open.scrollIntoView();},30);}
  }
  window.addEventListener('hashchange',function(){apply();if(phone.matches)window.scrollTo(0,0);});
  (phone.addEventListener||phone.addListener).call(phone,'change',apply);
  function folds(){document.querySelectorAll('.settings .fs,#notify .fs').forEach(function(d,i){if(phone.matches&&i>0&&!d.dataset.touched)d.open=false;});}
  document.addEventListener('toggle',function(e){if(e.target.classList&&e.target.classList.contains('fs'))e.target.dataset.touched='1';},true);
  apply();folds();
  // the confirmation flash travels in the address (?ok=...): drop it once shown, so a later reload does not repeat a message about an old click
  if(/[?&](ok|err)=/.test(location.search)&&history.replaceState)history.replaceState(null,'',location.pathname+location.hash);

  // confirm dangerous buttons (post now, discard), count caption characters and hashtags while typing
  document.addEventListener('click',function(e){if(e.target.closest('[data-reload]'))location.reload();});
  document.addEventListener('click',function(e){var b=e.target.closest('button[data-confirm]');if(b&&!window.confirm(b.dataset.confirm))e.preventDefault();});
  document.addEventListener('input',function(e){
    var t=e.target;if(!t.matches||!t.matches('textarea[data-caption]'))return;
    var card=t.closest('.ready'),txt=t.value;
    card.querySelector('[data-len]').textContent=txt.replace(/#[\p{L}\p{N}_]+/gu,'').trim().length;
    card.querySelector('[data-tags]').textContent=(txt.match(/#[\p{L}\p{N}_]+/gu)||[]).length;
  });
  // Product chat: one thread for words, files and links. Files stay in memory (never in browser storage); answers are polled while one is
  // being worked on and the thread is replaced in place, so a screen reader keeps its place.
  var chat=document.querySelector('[data-chat]'),chatFiles=[];
  if(chat){
    var form=chat.querySelector('[data-chat-form]'),csrf=chat.dataset.csrf,status=chat.querySelector('[data-chat-message]');
    var thread=function(){return document.getElementById('chat-thread');};
    var say=function(text){if(status)status.textContent=text||'';};
    var toBottom=function(){var t=thread();t.scrollTop=t.scrollHeight;};
    var post=async function(url,body){
      var response=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      var data=await response.json().catch(function(){return {};});
      if(!response.ok)throw Error(data.error||'Không thực hiện được');
      return data;
    };
    var refresh=function(){
      return fetch('/fragment/chat',{cache:'no-store'}).then(function(r){return r.ok?r.text():null;}).then(function(html){
        if(!html)return;
        var t=thread(),near=t.scrollHeight-t.scrollTop-t.clientHeight<80,tmp=document.createElement('div');
        tmp.innerHTML=html;var fresh=tmp.firstElementChild;
        if(fresh.innerHTML!==t.innerHTML){t.innerHTML=fresh.innerHTML;if(near)toBottom();}
        t.dataset.busy=fresh.dataset.busy;
      }).catch(function(){});
    };
    setInterval(function(){var t=thread();if(t&&t.dataset.busy==='1')refresh();},2500);
    toBottom();
    chat.addEventListener('click',function(e){
      var b=e.target.closest('button[data-chat-act]'),c=e.target.closest('[data-copy]');
      if(c){
        var box=c.parentNode.querySelector('input'),done=function(){c.textContent='Đã chép';setTimeout(function(){c.textContent='Chép link';},1800);};
        box.select();
        if(navigator.clipboard&&navigator.clipboard.writeText)navigator.clipboard.writeText(box.value).then(done,function(){document.execCommand('copy');done();});
        else{document.execCommand('copy');done();}
        return;
      }
      if(!b)return;
      var act=b.dataset.chatAct,payload={csrf:csrf,action:act,account:form?form.elements.account.value:''};
      if(act==='fill'){if(form){form.elements.text.value=b.dataset.text||'';form.elements.text.focus();}return;}
      if(b.dataset.id)payload.id=+b.dataset.id;
      if(b.dataset.source)payload.source=b.dataset.source;
      if(b.dataset.human)payload.human=true;
      if(act==='pick'){
        var tick=b.closest('article').querySelector('[data-chat-confirm]');
        if(!tick.checked){say('Hãy xem video rồi tích ô xác nhận trước khi chọn.');tick.focus();return;}
        payload.confirmed=true;payload.source_id=b.dataset.sourceId;payload.platform=b.dataset.platform;
      }
      b.disabled=true;say('Đang gửi…');
      post('/chat/act',payload).then(function(){say('');return refresh();}).catch(function(error){say(error.message);b.disabled=false;});
    });
  }
  if(chat&&form){
    var picker=form.elements.files,list=form.querySelector('[data-chat-files]'),textbox=form.elements.text;
    var showFiles=function(){
      list.replaceChildren();
      chatFiles.forEach(function(f,i){
        var li=document.createElement('li'),drop=document.createElement('button');
        li.textContent='📎 '+f.name+' ('+Math.round(f.size/1024)+' KiB)';
        drop.type='button';drop.className='ghost';drop.textContent='✕';drop.setAttribute('aria-label','Bỏ tệp '+f.name);
        drop.addEventListener('click',function(){chatFiles.splice(i,1);showFiles();});
        li.appendChild(drop);list.appendChild(li);
      });
    };
    var addFiles=function(files){
      var next=chatFiles.concat(Array.from(files));
      if(next.length>3||next.some(function(f){return f.size>4*1024*1024;})||next.reduce(function(n,f){return n+f.size;},0)>8*1024*1024){say('Tối đa 3 tệp, 4 MiB/tệp, tổng 8 MiB.');return;}
      if(next.some(function(f){return !/\.(png|jpe?g|webp|pdf|docx|txt)$/i.test(f.name);})){say('Chỉ nhận PNG/JPEG/WebP, PDF, DOCX hoặc TXT.');return;}
      chatFiles=next;say('');dirty=true;showFiles();
    };
    var readFile=function(f){return new Promise(function(resolve,reject){var r=new FileReader();r.onerror=function(){reject(Error('Không đọc được tệp'));};r.onload=function(){resolve({name:f.name,data:String(r.result).split(',')[1]});};r.readAsDataURL(f);});};
    form.querySelector('[data-chat-attach]').addEventListener('click',function(){picker.click();});
    picker.addEventListener('change',function(){addFiles(picker.files);picker.value='';});
    chat.addEventListener('dragover',function(e){e.preventDefault();chat.classList.add('over');});
    chat.addEventListener('dragleave',function(e){if(!chat.contains(e.relatedTarget))chat.classList.remove('over');});
    chat.addEventListener('drop',function(e){
      e.preventDefault();chat.classList.remove('over');
      if(e.dataTransfer.files.length)addFiles(e.dataTransfer.files);
      else{var dropped=e.dataTransfer.getData('text/uri-list')||e.dataTransfer.getData('text/plain');if(dropped){textbox.value+=(textbox.value?'\n':'')+dropped;dirty=true;}}
    });
    chat.addEventListener('paste',function(e){
      var pasted=Array.from(e.clipboardData.items||[]).filter(function(i){return i.kind==='file';}).map(function(i){return i.getAsFile();}).filter(Boolean);
      if(pasted.length){e.preventDefault();addFiles(pasted);}
    });
    textbox.addEventListener('keydown',function(e){if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();form.requestSubmit();}});
    document.addEventListener('click',function(e){var a=e.target.closest('[data-search-account]');if(a)form.elements.account.value=a.dataset.searchAccount;});
    form.addEventListener('submit',async function(e){
      e.preventDefault();e.stopPropagation();
      var text=textbox.value.trim();
      if(form.dataset.sent)return;
      if(!text&&!chatFiles.length){say('Hãy nhập mô tả, dán link hoặc thêm tệp.');return;}
      form.dataset.sent='1';var send=form.querySelector('button.send');send.disabled=true;say('Đang gửi…');
      try{
        var encoded=await Promise.all(chatFiles.map(readFile));
        await post('/chat/send',{csrf:csrf,account:form.elements.account.value,text:text,files:encoded});
        textbox.value='';chatFiles=[];showFiles();dirty=false;say('');await refresh();toBottom();
      }catch(error){say(error.message);}
      finally{delete form.dataset.sent;send.disabled=false;}
    });
  }

  // one click, one action: a second click while the first is being sent does nothing
  document.addEventListener('submit',function(e){
    var f=e.target;if(f.dataset.sent){e.preventDefault();return;}
    f.dataset.sent='1';setTimeout(function(){f.querySelectorAll('button').forEach(function(b){b.disabled=true;});},0);
  });
  var dirty=false;
  document.addEventListener('input',function(e){if(e.target.closest&&e.target.closest('form'))dirty=true;});

  // live progress of a running task: poll a small fragment; when it finishes, reload once to refresh every list
  function poll(){
    var panels=document.querySelectorAll('.taskpanel[data-running="1"]');
    if(!panels.length)return;
    fetch('/fragment/tasks',{cache:'no-store'}).then(function(r){return r.ok?r.text():null;}).then(function(html){
      if(!html)return;
      var tmp=document.createElement('div');tmp.innerHTML=html;var fresh=tmp.firstElementChild;
      if(fresh.dataset.running==='0'){location.reload();return;}
      panels.forEach(function(p){p.replaceWith(fresh.cloneNode(true));});
    }).catch(function(){});
  }
  setInterval(poll,2500);

  // idle refresh (no task, no typing, no playing media, tab visible) so numbers never go stale
  setInterval(function(){
    var a=document.activeElement,playing=false,panel=document.querySelector('.taskpanel[data-running="1"]');
    document.querySelectorAll('video,audio').forEach(function(v){if(!v.paused)playing=true;});
    var talking=document.getElementById('chat-thread');
    if(!dirty&&!playing&&!document.hidden&&!panel&&!(talking&&talking.dataset.busy==='1')&&!(a&&/^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName)))location.reload();
  },90000);
})();
