(function(){
  var phone=window.matchMedia('(max-width:959px)'),tabs=['home','queue','publish','attention','posted','more'];
  function tabOf(hash){
    var h=(hash||'').replace('#','');
    if(h==='search')return {tab:'queue',open:document.getElementById('search')};
    if(tabs.indexOf(h)>=0)return {tab:h};
    var el=h&&document.getElementById(h);
    if(el){var s=el.closest('section[data-tab]');if(s)return {tab:s.dataset.tab,open:el};}
    return {tab:'home'};
  }
  function apply(){
    document.body.classList.add('tabs');
    var r=tabOf(location.hash),cur=r.tab;
    document.querySelectorAll('section[data-tab]').forEach(function(s){s.classList.toggle('on',s.dataset.tab===cur);s.setAttribute('aria-hidden',s.dataset.tab===cur?'false':'true');});
    document.querySelectorAll('[data-go]').forEach(function(a){var active=a.dataset.go===cur;a.classList.toggle('on',active);if(active)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
    var searchMode=location.hash==='#search';
    document.querySelectorAll('[data-queue-pane]').forEach(function(p){p.hidden=(p.dataset.queuePane==='search')!==searchMode;});
    document.querySelectorAll('[data-queue-mode]').forEach(function(a){var on=(a.dataset.queueMode==='search')===searchMode;a.classList.toggle('on',on);if(on)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
    if(r.open&&r.open.tagName==='DETAILS'){r.open.open=true;if(phone.matches)setTimeout(function(){r.open.scrollIntoView();},30);}
  }
  function saveScroll(el){
    try{
      sessionStorage.setItem('trendvn.scroll.y',String(window.scrollY));
      var node=el&&(el.id?el:el.closest('[id]'));
      if(node&&node.id)sessionStorage.setItem('trendvn.scroll.target',node.id);
    }catch(e){}
  }
  function restoreScroll(){
    try{
      var targetId=sessionStorage.getItem('trendvn.scroll.target'),savedY=sessionStorage.getItem('trendvn.scroll.y');
      sessionStorage.removeItem('trendvn.scroll.target');sessionStorage.removeItem('trendvn.scroll.y');
      if(targetId){
        var el=document.getElementById(targetId);
        if(el){el.scrollIntoView({behavior:'smooth',block:'nearest'});return;}
      }
      var flash=document.querySelector('.flash,.banner.good,.banner.warn');
      if(flash&&/[?&](ok|err)=/.test(location.search)){flash.scrollIntoView({behavior:'smooth',block:'nearest'});return;}
      if(savedY!==null&&!isNaN(+savedY))window.scrollTo({top:+savedY,behavior:'instant'});
    }catch(e){}
  }
  window.addEventListener('hashchange',function(e){
    apply();
    var isNav=document.activeElement&&document.activeElement.closest('.topnav,.bottomnav');
    if(isNav)window.scrollTo(0,0);
    else restoreScroll();
  });
  (phone.addEventListener||phone.addListener).call(phone,'change',apply);
  function folds(){document.querySelectorAll('.settings .fs,#notify .fs').forEach(function(d,i){if(phone.matches&&i>0&&!d.dataset.touched)d.open=false;});}
  document.addEventListener('toggle',function(e){if(e.target.classList&&e.target.classList.contains('fs'))e.target.dataset.touched='1';},true);
  apply();folds();restoreScroll();
  // the confirmation flash travels in the address (?ok=...): drop it once shown, so a later reload does not repeat a message about an old click
  if(/[?&](ok|err)=/.test(location.search)&&history.replaceState)history.replaceState(null,'',location.pathname+location.hash);

  // confirm dangerous buttons (post now, discard), count caption characters and hashtags while typing
  document.addEventListener('click',function(e){if(e.target.closest('[data-reload]'))location.reload();});
  function askConfirmation(message){
    var modal=document.getElementById('confirm-action');
    if(!modal||modal.open)return Promise.resolve(false);
    modal.querySelector('#confirm-message').textContent=message;
    return new Promise(function(resolve){
      modal.addEventListener('close',function(){resolve(modal.returnValue==='confirm');},{once:true});
      modal.querySelector('[data-confirm-cancel]').onclick=function(){modal.close('cancel');};
      modal.querySelector('[data-confirm-accept]').onclick=function(){modal.close('confirm');};
      modal.returnValue='cancel';modal.showModal();
    });
  }
  document.addEventListener('click',function(e){
    var b=e.target.closest('button[data-confirm]');
    if(!b||b.dataset.confirmed)return;
    e.preventDefault();
    askConfirmation(b.dataset.confirm).then(function(ok){if(ok&&b.isConnected){saveScroll(b);b.dataset.confirmed='1';b.click();delete b.dataset.confirmed;}});
  });
  document.addEventListener('input',function(e){
    var t=e.target;if(!t.matches||!t.matches('textarea[data-caption]'))return;
    var card=t.closest('.ready'),txt=t.value;
    card.querySelector('[data-len]').textContent=txt.replace(/#[\p{L}\p{N}_]+/gu,'').trim().length;
    card.querySelector('[data-tags]').textContent=(txt.match(/#[\p{L}\p{N}_]+/gu)||[]).length;
  });
  // Product chat: one thread for words, files and links. Files stay in memory (never in browser storage); answers are polled while one is
  // being worked on and the thread's content is replaced inside the same log element (a ticked confirmation survives the refresh).
  var chat=document.querySelector('[data-chat]'),chatFiles=[],draftRevision=0;
  function markDraftChanged(){draftRevision++;if(form)delete form.dataset.requestKey;}
  if(chat){
    var form=chat.querySelector('[data-chat-form]'),csrf=chat.dataset.csrf,status=chat.querySelector('[data-chat-message]');
    var thread=function(){return document.getElementById('chat-thread');};
    var say=function(text){if(status)status.textContent=text||'';};
    var toBottom=function(){var t=thread();t.scrollTop=t.scrollHeight;};
    var post=async function(url,body){
      if(body&&typeof body==='object'&&'csrf' in body)body.csrf=csrf;
      var response=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      var data=await response.json().catch(function(){return {};});
      if(response.status===403&&data.error&&data.error.indexOf('Trang đã cũ')>=0){
        await refresh(false);
        if(body&&typeof body==='object'&&'csrf' in body)body.csrf=csrf;
        response=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
        data=await response.json().catch(function(){return {};});
      }
      if(!response.ok)throw Error(data.error||'Không thực hiện được');
      return data;
    };
    var tickKey=function(box){var b=box.closest('article').querySelector('[data-chat-act="pick"]');return b?b.dataset.id+'|'+b.dataset.sourceId+'|'+b.dataset.platform:'';};
    var refreshing=null,queueNeedsUpdate=false;
    var refreshQueue=function(){document.dispatchEvent(new Event('trendvn:queue'));return Promise.resolve();};
    var refresh=function(afterMutation,removeHistory){
      if(refreshing)return afterMutation?refreshing.then(function(){return refresh(true,removeHistory);}):refreshing;
      refreshing=fetch('/fragment/chat',{cache:'no-store'}).then(function(r){
        var token=r.headers.get('x-csrf-token');
        if(token){csrf=token;if(chat)chat.dataset.csrf=token;}
        return r.ok?r.text():null;
      }).then(function(html){
        if(!html)return;
        var t=thread(),side=document.getElementById('chat-side'),near=t.scrollHeight-t.scrollTop-t.clientHeight<80,oldTop=t.scrollTop,tmp=document.createElement('div');
        var anchor=Array.from(t.querySelectorAll('[data-message-id]')).find(function(el){return el.offsetTop+el.offsetHeight>t.offsetTop+t.scrollTop;}),anchorId=anchor&&anchor.dataset.messageId,anchorOffset=anchor&&anchor.offsetTop-t.scrollTop;
        tmp.innerHTML=html;var fresh=tmp.querySelector('#chat-thread'),freshSide=tmp.querySelector('#chat-side');
        var playing=Array.from(t.querySelectorAll('video,audio')).some(function(v){return !v.paused;});
        if(fresh.innerHTML!==t.innerHTML&&(!playing||removeHistory)&&!document.querySelector('dialog[open]')){
          var ticked=Array.from(t.querySelectorAll('[data-chat-confirm]:checked')).map(tickKey);
          t.innerHTML=fresh.innerHTML;
          t.querySelectorAll('[data-chat-confirm]').forEach(function(box){if(ticked.indexOf(tickKey(box))>=0)box.checked=true;});
          if(near)toBottom();
          else{var same=anchorId&&t.querySelector('[data-message-id="'+anchorId+'"]');t.scrollTop=same?same.offsetTop-anchorOffset:oldTop;}
        }
        var wasBusy=t.dataset.busy==='1';t.dataset.busy=fresh.dataset.busy;
        if(side&&freshSide&&freshSide.innerHTML!==side.innerHTML&&!document.querySelector('dialog[open]')&&(afterMutation||!side.contains(document.activeElement))){side.innerHTML=freshSide.innerHTML;accountChannels();}
        if(t.dataset.busy==='0'&&(wasBusy||queueNeedsUpdate)){queueNeedsUpdate=false;return refreshQueue();}
      }).catch(function(){}).finally(function(){refreshing=null;});
      return refreshing;
    };
    setInterval(function(){var t=thread();if(!document.hidden&&t&&t.dataset.busy==='1')refresh();},2500);
    document.addEventListener('trendvn:state',function(){refresh();});
    toBottom();
    // on a phone the other tabs are hidden: the thread has no height until its tab is shown, so go to its end then
    window.addEventListener('hashchange',function(){if(tabOf(location.hash).tab==='queue')setTimeout(toBottom,50);});
    chat.addEventListener('click',async function(e){
      var b=e.target.closest('button[data-chat-act]'),c=e.target.closest('[data-copy]');
      if(c){
        var box=c.parentNode.querySelector('input'),done=function(){c.textContent='Đã chép';setTimeout(function(){c.textContent='Chép link';},1800);};
        box.select();
        if(navigator.clipboard&&navigator.clipboard.writeText)navigator.clipboard.writeText(box.value).then(done,function(){document.execCommand('copy');done();});
        else{document.execCommand('copy');done();}
        return;
      }
      if(!b)return;
      var act=b.dataset.chatAct,payload={csrf:csrf,action:act};  // the account is the one the message was sent for, decided by the server
      if(act==='fill'){if(form){form.elements.text.value=b.dataset.text||'';markDraftChanged();form.elements.text.focus();}return;}
      if(act==='quick_find'){
        var q=b.dataset.query||'',cat=b.dataset.category||'',src=b.dataset.source||'douyin',acct=b.dataset.account||form.elements.account.value;
        if(form){
          form.elements.text.value=q;form.elements.sales.checked=true;
          form.querySelector('[data-sales-category]').hidden=false;form.elements.category.value=cat;
          form.elements.source.value=src;if(acct)form.elements.account.value=acct;
          markDraftChanged();form.requestSubmit();
        }
        return;
      }
      if(act==='refresh_check'){
        b.disabled=true;say('Đang kiểm tra tiến độ tìm kiếm và giải CAPTCHA…');
        refresh(true).then(function(){say('Đã cập nhật trạng thái');}).catch(function(){}).finally(function(){b.disabled=false;});
        return;
      }
      if(act==='toggle_batch_all'){
        var cont=b.closest('.top-products-container')||b.closest('.bubble');
        if(cont){
          var checks=cont.querySelectorAll('input.batch-product-check');
          var allChecked=Array.from(checks).every(function(c){return c.checked;});
          checks.forEach(function(c){c.checked=!allChecked;});
          var countSpans=cont.querySelectorAll('[data-batch-count]');
          countSpans.forEach(function(s){s.textContent=allChecked?'0':checks.length;});
          b.textContent=allChecked?'Chọn tất cả':'Bỏ chọn tất cả';
        }
        return;
      }
      if(act==='batch_find'){
        var cont=b.closest('.top-products-container')||b.closest('.bubble');
        var checks=cont?Array.from(cont.querySelectorAll('input.batch-product-check:checked')):[],items=[];
        checks.forEach(function(c){
          try{items.push(JSON.parse(c.dataset.product));}catch(e){}
        });
        if(!items.length){say('Hãy chọn ít nhất 1 sản phẩm để tìm kiếm hàng loạt.');return;}
        payload.products=items;
      }
      if(b.dataset.ask&&!await askConfirmation(b.dataset.ask))return;
      if(b.dataset.id)payload.id=+b.dataset.id;
      if(b.dataset.channel)payload.channel=b.dataset.channel;
      if(b.dataset.account)payload.account=b.dataset.account;
      if(b.dataset.productId)payload.product_id=b.dataset.productId;
      if(b.dataset.source)payload.source=b.dataset.source;
      if(b.dataset.query)payload.query=b.dataset.query;
      if(b.dataset.category)payload.category=b.dataset.category;
      if(b.dataset.sales)payload.sales=true;
      if(b.dataset.human)payload.human=true;
      if(b.dataset.itemKey)payload.item_key=b.dataset.itemKey;
      if(act==='dismiss'){payload.source_id=b.dataset.sourceId;payload.platform=b.dataset.platform;}
      if(act==='pick'){
        var tick=b.closest('article').querySelector('[data-chat-confirm]');
        if(!tick.checked){say('Hãy xem video rồi tích ô xác nhận trước khi chọn.');tick.focus();return;}
        payload.confirmed=true;payload.source_id=b.dataset.sourceId;payload.platform=b.dataset.platform;
        queueNeedsUpdate=true;
      }
      var bubble=b.closest('.bubble')||b.parentNode,feedback=bubble.querySelector('[data-action-feedback]');
      if(!feedback){feedback=document.createElement('p');feedback.dataset.actionFeedback='1';feedback.setAttribute('role','status');feedback.setAttribute('aria-live','polite');bubble.appendChild(feedback);}
      b.disabled=true;feedback.textContent='Đang thực hiện…';say('Đang gửi…');
      post('/chat/act',payload).then(function(){feedback.textContent='Đã thực hiện';say('');return refresh(true,act==='clear'||act==='delete_history');}).catch(function(error){feedback.textContent=error.message;say(error.message);}).then(function(){b.disabled=false;});
    });
    chat.addEventListener('change',function(e){
      if(e.target.matches('input.batch-product-check')){
        var cont=e.target.closest('.top-products-container')||e.target.closest('.bubble');
        if(cont){
          var checked=cont.querySelectorAll('input.batch-product-check:checked').length;
          var countSpans=cont.querySelectorAll('[data-batch-count]');
          countSpans.forEach(function(s){s.textContent=checked;});
        }
      }
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
        drop.addEventListener('click',function(){chatFiles.splice(i,1);markDraftChanged();showFiles();});
        li.appendChild(drop);list.appendChild(li);
      });
    };
    var addFiles=function(files){
      var next=chatFiles.concat(Array.from(files));
      if(next.length>3||next.some(function(f){return f.size>4*1024*1024;})||next.reduce(function(n,f){return n+f.size;},0)>8*1024*1024){say('Tối đa 3 tệp, 4 MiB/tệp, tổng 8 MiB.');return;}
      if(next.some(function(f){return !/\.(png|jpe?g|webp|pdf|docx|txt)$/i.test(f.name);})){say('Chỉ nhận PNG/JPEG/WebP, PDF, DOCX hoặc TXT.');return;}
      chatFiles=next;markDraftChanged();say('');showFiles();
    };
    var readFile=function(f){return new Promise(function(resolve,reject){var r=new FileReader();r.onerror=function(){reject(Error('Không đọc được tệp'));};r.onload=function(){resolve({name:f.name,data:String(r.result).split(',')[1]});};r.readAsDataURL(f);});};
    form.querySelector('[data-chat-attach]').addEventListener('click',function(){picker.click();});
    picker.addEventListener('change',function(){addFiles(picker.files);picker.value='';});
    chat.addEventListener('dragover',function(e){e.preventDefault();chat.classList.add('over');});
    chat.addEventListener('dragleave',function(e){if(!chat.contains(e.relatedTarget))chat.classList.remove('over');});
    chat.addEventListener('drop',function(e){
      e.preventDefault();chat.classList.remove('over');
      if(e.dataTransfer.files.length)addFiles(e.dataTransfer.files);
      else{var dropped=e.dataTransfer.getData('text/uri-list')||e.dataTransfer.getData('text/plain');if(dropped){textbox.value+=(textbox.value?'\n':'')+dropped;markDraftChanged();}}
    });
    chat.addEventListener('paste',function(e){
      var pasted=Array.from(e.clipboardData.items||[]).filter(function(i){return i.kind==='file';}).map(function(i){return i.getAsFile();}).filter(Boolean);
      if(pasted.length){e.preventDefault();addFiles(pasted);}
    });
    form.elements.sales.addEventListener('change',function(){var enabled=form.elements.sales.checked;form.querySelector('[data-sales-category]').hidden=!enabled;form.elements.category.required=enabled;});
    form.addEventListener('input',markDraftChanged);
    textbox.addEventListener('keydown',function(e){if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();form.requestSubmit();}});
    document.addEventListener('click',function(e){var a=e.target.closest('[data-search-account]');if(a){form.elements.account.value=a.dataset.searchAccount;accountTopic();markDraftChanged();}});
    try{var saved=sessionStorage.getItem('trendvn.chat.account');if(saved&&Array.from(form.elements.account.options).some(function(o){return o.value===saved;}))form.elements.account.value=saved;}catch(e){}
    var accountTopics=JSON.parse(form.querySelector('[data-account-topics]').dataset.accountTopics);
    function accountChannels(){
      if(!form)return;
      document.querySelectorAll('[data-channel-account]').forEach(function(row){row.hidden=row.dataset.channelAccount!==form.elements.account.value;});
    }
    function accountTopic(){form.elements.topic.value=accountTopics[form.elements.account.value]||'';accountChannels();}
    accountTopic();
    form.elements.account.addEventListener('change',function(){accountTopic();try{sessionStorage.setItem('trendvn.chat.account',form.elements.account.value);}catch(e){}});
    // crypto.randomUUID exists only on a secure page (https or localhost); the dashboard is also opened as http://<vpn address>
    var newKey=function(){
      try{if(window.crypto&&crypto.randomUUID)return crypto.randomUUID();}catch(e){}
      var bytes=new Uint8Array(16);
      try{crypto.getRandomValues(bytes);}catch(e){for(var i=0;i<16;i++)bytes[i]=Math.floor(Math.random()*256);}
      return Array.prototype.map.call(bytes,function(b){return ('0'+b.toString(16)).slice(-2);}).join('');
    };
    form.addEventListener('submit',async function(e){
      e.preventDefault();e.stopPropagation();
      var text=textbox.value.trim();
      if(form.dataset.sent)return;
      if(!text&&!chatFiles.length&&!form.elements.topic.value&&!form.elements.sales.checked){say('Hãy nhập từ khóa, chọn thể loại/ngành hàng hoặc thêm tệp.');return;}
      var revision=draftRevision,requestKey=form.dataset.requestKey||(form.dataset.requestKey=newKey());
      var allowDup=form.dataset.allowDuplicate==='1';delete form.dataset.allowDuplicate;
      var payload={csrf:csrf,request_key:requestKey,account:form.elements.account.value,source:form.elements.source.value,topic:form.elements.topic.value,sales:form.elements.sales.checked,category:form.elements.category.value,text:text,allow_duplicate:allowDup};
      form.dataset.sent='1';var send=form.querySelector('button.send');send.disabled=true;say('Đang gửi…');
      try{
        var encoded=await Promise.all(chatFiles.map(readFile));
        payload.files=encoded;await post('/chat/send',payload);
        if(revision===draftRevision){delete form.dataset.requestKey;textbox.value='';chatFiles=[];showFiles();}
        say('');await refresh(true);toBottom();
      }catch(error){say(error.message);}
      finally{delete form.dataset.sent;send.disabled=false;}
    });
  }

  // one click, one action: a second click while the first is being sent does nothing
  document.addEventListener('submit',function(e){
    var f=e.target;if(f.dataset.sent){e.preventDefault();return;}
    saveScroll(f);
    f.dataset.sent='1';setTimeout(function(){f.querySelectorAll('button').forEach(function(b){b.disabled=true;});},0);
  });
})();
