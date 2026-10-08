"""Observe positive deletion notices before the click, including short-lived toasts with close controls."""

SUCCESS = r"^(Video deleted\.?|Your video has been deleted\.?|Post deleted\.?|Đã xóa video\.?|Đã xóa bài đăng\.?)$"

ARM = """pattern => {
  const key='__trendvnDeleteProof';
  if(window[key]?.observer)window[key].observer.disconnect();
  const state={proof:''}, match=new RegExp(pattern,'i');
  const visible=element => {
    if(!element?.getClientRects().length||element.closest('[hidden],[aria-hidden="true"]'))return false;
    for(let e=element;e;e=e.parentElement){
      const style=getComputedStyle(e);
      if(style.visibility!=='visible'||style.opacity==='0')return false;
    }
    return true;
  };
  const inspect=node => {
    const parent=node.nodeType===3 ? node.parentElement : node;
    const notice=parent?.closest?.('[role="alert"],[role="status"],[data-e2e="toast-message"],[data-sonner-toast],[aria-label^="Notifications"]');
    const text=(node.textContent||'').trim().replace(/\\s+/g,' ');
    if(node.nodeType===3&&notice&&visible(parent)&&match.test(text))state.proof=text;
    if(node.nodeType!==3)for(const child of node.childNodes)inspect(child);
  };
  state.observer=new MutationObserver(records => {
    for(const record of records){
      if(record.type==='characterData')inspect(record.target);
      for(const node of record.addedNodes)inspect(node);
    }
  });
  state.observer.observe(document.body,{childList:true,subtree:true,characterData:true});
  window[key]=state;
}"""
READY = "() => Boolean(window.__trendvnDeleteProof?.proof)"
STOP = """() => {
  const state=window.__trendvnDeleteProof;
  state?.observer.disconnect();
  delete window.__trendvnDeleteProof;
}"""


def arm_notice(page):
    page.evaluate(ARM, SUCCESS)


def wait_notice(page):
    try:
        page.wait_for_function(READY, timeout=15000)
    finally:
        page.evaluate(STOP)
