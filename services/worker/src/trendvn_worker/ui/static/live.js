/* Refresh the current screen without losing forms, media or confirmation dialogs. */
(function(){
  var timer=null,inflight=false,again=false,busy=false,lastChat=0,failures=0;
  function activeTab(){var tab=document.querySelector('section[data-tab].on');return tab?tab.dataset.tab:'home';}
  function status(text){var el=document.getElementById('live-status');el.textContent=text;el.hidden=!text;}
  function protectedRegion(el){
    var a=document.activeElement;
    return document.querySelector('dialog[open]')||el.querySelector('form[data-edited]')||
      (a&&el.contains(a)&&a.matches('input,textarea,select,summary'))||
      Array.from(el.querySelectorAll('video,audio')).some(function(v){return !v.paused;});
  }
  function updateBadges(badges){
    document.querySelectorAll('[data-go]').forEach(function(a){
      var tab=a.dataset.go,n=badges[tab]||0,badge=a.querySelector('i');
      if(!n){if(badge)badge.remove();return;}
      if(!badge){badge=document.createElement('i');badge.className=tab==='attention'?'':'n';(a.querySelector('.ic')||a).appendChild(badge);}
      badge.textContent=n;
    });
    document.querySelectorAll('[data-waiting-count]').forEach(function(el){el.textContent=badges.queue||0;});
  }
  function replaceRegion(el,html){
    if(el.dataset.liveHtml===html)return true;
    if(protectedRegion(el))return false;
    var open=Array.from(el.querySelectorAll('details[open][id]')).map(function(d){return d.id;});
    if(el.id==='queue-live'){
      var tmp=document.createElement('div');tmp.innerHTML=html;var fresh=tmp.querySelector('#queue-live');if(!fresh)return true;
      el.innerHTML=fresh.innerHTML;
    }else el.innerHTML=html;
    open.forEach(function(id){var d=document.getElementById(id);if(d&&el.contains(d))d.open=true;});
    el.dataset.liveHtml=html;return true;
  }
  async function poll(){
    clearTimeout(timer);
    if(document.hidden)return;
    if(inflight){again=true;return;}
    inflight=true;again=false;
    var tab=activeTab(),controller=new AbortController(),deadline=setTimeout(function(){controller.abort();},10000);
    try{
      var response=await fetch('/fragment/live?tab='+encodeURIComponent(tab),{cache:'no-store',signal:controller.signal});
      if(!response.ok)throw Error('refresh');
      var data=await response.json();
      if(document.hidden||tab!==activeTab())return;
      failures=0;busy=data.running;updateBadges(data.badges);
      document.querySelector('[data-clock]').textContent=data.clock;
      var region=tab==='queue'?document.getElementById('queue-live'):document.getElementById(tab);
      status(data.html&&!replaceRegion(region,data.html)?'Có cập nhật mới. Nội dung sẽ đổi sau khi bạn lưu hoặc xem xong.':'');
      if(tab==='queue'&&Date.now()-lastChat>10000){lastChat=Date.now();document.dispatchEvent(new Event('trendvn:state'));}
    }catch(error){
      failures++;if(tab===activeTab())status('Chưa cập nhật được trạng thái. Hệ thống sẽ tự kết nối lại; nội dung đang nhập được giữ.');
    }finally{
      clearTimeout(deadline);inflight=false;
      timer=setTimeout(poll,again||tab!==activeTab()?0:(failures?30000:(busy?2500:15000)));
    }
  }
  document.addEventListener('input',function(e){var f=e.target.closest('form');if(f&&f.closest('#publish'))f.dataset.edited='1';});
  document.addEventListener('change',function(e){var f=e.target.closest('form');if(f&&f.closest('#publish'))f.dataset.edited='1';});
  window.addEventListener('hashchange',poll);
  document.addEventListener('visibilitychange',function(){if(document.hidden)clearTimeout(timer);else poll();});
  document.addEventListener('trendvn:queue',poll);
  poll();
})();
