(function(){'use strict';if(window.__hpLoadingInit)return;window.__hpLoadingInit=true;var OVERLAY_ID='hp-global-loading-overlay';var MAX_SHOW_MS=45000;var showTime=0;var pendingRequests=0;var slowConnection=false;function getLoaderType(){try{return localStorage.getItem('hp_loader_type')||'code';}
catch(e){return'code';}}
function checkSlowConnection(){try{if(navigator.connection||navigator.mozConnection||navigator.webkitConnection){var conn=navigator.connection||navigator.mozConnection||navigator.webkitConnection;var type=conn.effectiveType;slowConnection=(type==='slow-2g'||type==='2g'||type==='3g');return slowConnection;}}catch(e){}
return false;}
function initNetworkMonitoring(){try{var origOpen=XMLHttpRequest.prototype.open;var origSend=XMLHttpRequest.prototype.send;XMLHttpRequest.prototype.open=function(){this._requestStart=false;origOpen.apply(this,arguments);};XMLHttpRequest.prototype.send=function(){var xhr=this;if(!xhr._requestStart){xhr._requestStart=true;pendingRequests++;if(slowConnection||pendingRequests>0){show();}}
var onComplete=function(){if(xhr._requestStart){xhr._requestStart=false;pendingRequests=Math.max(0,pendingRequests-1);if(pendingRequests===0){setTimeout(function(){if(pendingRequests===0&&!hasSpinner()){hide();}},300);}}};xhr.addEventListener('load',onComplete);xhr.addEventListener('error',onComplete);xhr.addEventListener('abort',onComplete);origSend.apply(this,arguments);};if(window.fetch){var origFetch=window.fetch;window.fetch=function(){pendingRequests++;if(slowConnection||pendingRequests>0){show();}
return origFetch.apply(this,arguments).then(function(response){pendingRequests=Math.max(0,pendingRequests-1);if(pendingRequests===0){setTimeout(function(){if(pendingRequests===0&&!hasSpinner()){hide();}},300);}
return response;},function(error){pendingRequests=Math.max(0,pendingRequests-1);if(pendingRequests===0){setTimeout(function(){if(pendingRequests===0&&!hasSpinner()){hide();}},300);}
throw error;});};}}catch(e){}}
var LOADERS={hand:'<div class="hp-loader hp-loader-hand">'+
'<div class="hand-loader">'+
'<div class="hand-finger"></div><div class="hand-finger"></div>'+
'<div class="hand-finger"></div><div class="hand-finger"></div>'+
'<div class="hand-palm"></div><div class="hand-thumb"></div>'+
'</div>'+
'</div>',spinner:'<div class="hp-loader hp-loader-spinner">'+
'<div class="hp-spinner-dots">'+
'<div class="hp-dot"></div>'+
'<div class="hp-dot"></div>'+
'<div class="hp-dot"></div>'+
'</div>'+
'</div>',code:'<div class="hp-loader hp-loader-code">'+
'<div class="hp-code-loader">'+
'<span>&lt;</span>'+
'<span>LOADING...</span>'+
'<span>/&gt;</span>'+
'</div>'+
'</div>'};function getOverlay(){try{if(!document.body)return null;var el=document.getElementById(OVERLAY_ID);if(!el){el=document.createElement('div');el.id=OVERLAY_ID;el.className='hp-loading-overlay';document.body.appendChild(el);}
var type=getLoaderType();var currentType=el.getAttribute('data-loader');if(currentType!==type){el.innerHTML=LOADERS[type]||LOADERS.hand;el.setAttribute('data-loader',type);}
return el;}catch(err){return null;}}
function show(){try{var o=getOverlay();if(o){o.classList.add('show');if(showTime===0)showTime=Date.now();}}catch(err){}}
function hide(){try{showTime=0;var o=document.getElementById(OVERLAY_ID);if(o)o.classList.remove('show');}catch(err){}}
function hasSpinner(){try{var el=document.querySelector&&document.querySelector('.anvil-spinner');if(!el)return false;if(!el.isConnected)return false;if(el.offsetParent===null)return false;var p=el.parentElement;var steps=0;while(p&&p!==document.body&&steps<15){var s=window.getComputedStyle(p);if(s.display==='none'||s.visibility==='hidden'||parseFloat(s.opacity)<0.05)
return false;p=p.parentElement;steps++;}
return true;}catch(err){return false;}}
function tick(){try{if(!document.body)return;var overlay=document.getElementById(OVERLAY_ID);if(overlay&&overlay.classList.contains('show')&&showTime>0){if(Date.now()-showTime>MAX_SHOW_MS){hide();return;}}
if(hasSpinner()||pendingRequests>0){show();}else{hide();}}catch(err){hide();}}
var _tickTimer=0;var DEBOUNCE_MS=80;function debouncedTick(){if(_tickTimer)return;var delay=slowConnection?50:DEBOUNCE_MS;_tickTimer=setTimeout(function(){_tickTimer=0;tick();},delay);}
function start(){try{if(!document.body){setTimeout(start,100);return;}
checkSlowConnection();if(navigator.connection||navigator.mozConnection||navigator.webkitConnection){var conn=navigator.connection||navigator.mozConnection||navigator.webkitConnection;conn.addEventListener('change',checkSlowConnection);}
initNetworkMonitoring();if(typeof MutationObserver!=='undefined'){var observer=new MutationObserver(debouncedTick);observer.observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['class','style','hidden']});}
var fallbackInterval=slowConnection?1000:2000;setInterval(tick,fallbackInterval);tick();}catch(err){}}
if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',function(){setTimeout(start,200);});}else{setTimeout(start,200);}
window.showLoadingOverlay=show;window.hideLoadingOverlay=hide;window.setLoaderType=function(type){if(type!=='hand'&&type!=='spinner'&&type!=='code')return;try{localStorage.setItem('hp_loader_type',type);}catch(e){}
var el=document.getElementById(OVERLAY_ID);if(el)el.removeAttribute('data-loader');};window.getLoaderType=getLoaderType;window.isSlowConnection=function(){return slowConnection;};window.getPendingRequests=function(){return pendingRequests;};})();