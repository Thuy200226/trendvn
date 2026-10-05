(function(){
  var phone=window.matchMedia('(max-width:720px)'),tabs=['home','queue','publish','attention','posted','more'];
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
    if(!dirty&&!playing&&!document.hidden&&!panel&&!(a&&/^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName)))location.reload();
  },90000);
})();
