const I18N={en:{installApp:"Install App",heroState:"SYSTEM PROTECTED",heroSub:"AI Threat Intelligence & Heuristic Cyber Safety",urlTitle:"URL SCANNER",urlSub:"Redirect, TLD & phishing heuristics",scanUrlBtn:"⚡ Scan URL",textTitle:"SCAM MSG ANALYZER",textSub:"SMS / WhatsApp + Gujarati safety notes",scanTextBtn:"✨ Analyze Message",apkTitle:"APK STATIC INSPECTOR",apkSub:"SHA-256, ZIP & permission indicators",apkPick:"Choose .apk file (Max 25 MB)",scanApkBtn:"🛡️ Inspect APK",recentTitle:"RECENT SCANS",recentSub:"Saved on this device",clear:"Clear",noHistory:"No scans yet. Run a scan to see results here.",scanning:"Analyzing threat signals..."},gu:{installApp:"એપ ઇન્સ્ટોલ કરો",heroState:"સિસ્ટમ સુરક્ષિત છે",heroSub:"AI સાયબર સુરક્ષા અને હ્યુરિસ્ટિક તપાસ સક્રિય",urlTitle:"લિંક સ્કેનર (URL)",urlSub:"ફિશિંગ અને રિડાયરેક્ટ તપાસ",scanUrlBtn:"⚡ લિંક સ્કેન કરો",textTitle:"સ્કેમ મેસેજ તપાસ",textSub:"SMS / WhatsApp + ગુજરાતી સમજૂતી",scanTextBtn:"✨ મેસેજ તપાસો",apkTitle:"APK સ્ટેટિક તપાસ",apkSub:"SHA-256 અને પરમિશન તપાસ",apkPick:".apk ફાઇલ પસંદ કરો (25 MB)",scanApkBtn:"🛡️ APK તપાસો",recentTitle:"તાજેતરના સ્કેન",recentSub:"આ ફોનમાં સેવ થયેલ",clear:"સાફ કરો",noHistory:"હજુ સુધી કોઈ સ્કેન નથી.",scanning:"સુરક્ષા તપાસ ચાલી રહી છે..."}};
let lang="en",deferredPrompt=null;const HKEY="rakshak_scan_history_v3";
const esc=v=>String(v).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
function setLang(l){lang=l;const d=I18N[l]||I18N.en;document.querySelectorAll("[data-i18n]").forEach(e=>{const k=e.getAttribute("data-i18n");if(d[k])e.textContent=d[k];});document.getElementById("langToggle").textContent=l==="en"?"ગુજરાતી":"English";}
function getScore(d){for(const k of["risk_score","ai_risk_score","score","final_score","threat_score"]){if(typeof d[k]==="number")return d[k];if(typeof d[k]==="string"&&!Number.isNaN(Number(d[k])))return Number(d[k]);}return null;}
function showResult(type,target,data,mirrorId="resultCard"){
  const card=document.getElementById(mirrorId),sc=getScore(data);
  let bc="risk-low",bt="ANALYZED";
  if(sc!==null){if(sc>=70){bc="risk-high";bt=`HIGH RISK • ${sc}/100`;}else if(sc>=35){bc="risk-med";bt=`MEDIUM • ${sc}/100`;}else{bc="risk-low";bt=`LOW RISK • ${sc}/100`;}}
  else if(data.risk_level||data.verdict||data.status){const lb=String(data.risk_level||data.verdict||data.status);bt=lb.toUpperCase();if(/high|scam|danger|malicious|phish/i.test(lb))bc="risk-high";else if(/med|suspicious|warn/i.test(lb))bc="risk-med";}
  const guj=data.explanation_gujarati||data.gujarati_explanation||data.explanation||data.summary||"";
  const rows=Object.entries(data).filter(([k])=>!["explanation_gujarati","gujarati_explanation"].includes(k)).map(([k,v])=>{
    const f=Array.isArray(v)?(v.length?v.map(i=>`• ${esc(typeof i==="object"?JSON.stringify(i):i)}`).join("<br/>"):"None"):(v&&typeof v==="object"?`<pre style="white-space:pre-wrap;font-size:.78rem">${esc(JSON.stringify(v,null,2))}</pre>`:esc(v??"—"));
    return `<div class="kv-row"><div class="kv-key">${esc(k.replace(/_/g," "))}</div><div>${f}</div></div>`;
  }).join("");
  card.innerHTML=`<div class="result-header"><div><strong>${esc(type.toUpperCase())} RESULT</strong><div class="muted">${esc(target)}</div></div><span class="risk-badge ${bc}">${esc(bt)}</span></div>${guj?`<div class="gujarati-box"><strong>🇮🇳 Safety Note:</strong><br/>${esc(guj)}</div>`:""}<div class="kv-grid">${rows}</div>`;
  card.classList.remove("hidden");card.scrollIntoView({behavior:"smooth",block:"nearest"});
  const list=JSON.parse(localStorage.getItem(HKEY)||"[]");list.unshift({type,target,bt,bc});localStorage.setItem(HKEY,JSON.stringify(list.slice(0,8)));
  document.getElementById("lastScanText").textContent=`Last scan: ${new Date().toLocaleTimeString()}`;renderHistory();
}
function renderHistory(){
  const c=document.getElementById("historyList"),list=JSON.parse(localStorage.getItem(HKEY)||"[]");
  c.innerHTML=list.length?list.map(i=>`<div class="history-item"><div class="history-target"><strong>[${esc(i.type.toUpperCase())}]</strong> ${esc(i.target)}</div><span class="risk-badge ${esc(i.bc)}" style="font-size:.7rem;padding:3px 8px">${esc(i.bt)}</span></div>`).join(""):`<p class="muted">${esc(I18N[lang].noHistory)}</p>`;
}
async function runScan(ep,fd,type,label,targetCard="resultCard"){
  const ld=document.getElementById("loadingBox"),rc=document.getElementById(targetCard);
  ld.classList.remove("hidden");rc.classList.add("hidden");
  try{
    const r=await fetch(ep,{method:"POST",body:fd}),d=await r.json();
    if(!r.ok)throw new Error(d.detail||d.error||`Error (${r.status})`);
    showResult(type,label,d,targetCard);
  }catch(e){
    rc.innerHTML=`<div class="result-header"><strong>SCAN ERROR</strong><span class="risk-badge risk-high">FAILED</span></div><p class="muted">${esc(e.message)}</p>`;
    rc.classList.remove("hidden");
  }finally{ld.classList.add("hidden");}
}
document.addEventListener("DOMContentLoaded",()=>{
  const splash=document.getElementById("splashScreen");
  const hideSplash=()=>splash.classList.add("hide");
  setTimeout(hideSplash,1450);splash.addEventListener("click",hideSplash);
  fetch("/api/health").then(r=>{const b=document.getElementById("healthBadge");if(!r.ok)throw 0;b.textContent="● Live";b.className="status-pill online";}).catch(()=>{const b=document.getElementById("healthBadge");b.textContent="● Offline";b.className="status-pill offline";});
  renderHistory();
  document.querySelectorAll(".nav-item").forEach(btn=>btn.addEventListener("click",()=>{
    const v=btn.getAttribute("data-view");
    document.querySelectorAll(".nav-item").forEach(b=>b.classList.toggle("active",b===btn));
    document.querySelectorAll(".view").forEach(vw=>vw.classList.toggle("active",vw.id===`view-${v}`));
    window.scrollTo({top:0,behavior:"smooth"});
  }));
  document.getElementById("langToggle").addEventListener("click",()=>{setLang(lang==="en"?"gu":"en");renderHistory();});
  document.querySelectorAll("[data-fill-url]").forEach(b=>b.addEventListener("click",()=>document.getElementById("urlInput").value=b.getAttribute("data-fill-url")));
  document.querySelectorAll("[data-fill-text]").forEach(b=>b.addEventListener("click",()=>document.getElementById("textInput").value=b.getAttribute("data-fill-text")));
  document.getElementById("apkInput").addEventListener("change",e=>{const f=e.target.files[0];if(f)document.getElementById("apkFileLabel").textContent=`📦 ${f.name}`;});
  document.getElementById("imageInput").addEventListener("change",e=>{const f=e.target.files[0];if(f)document.getElementById("imgFileLabel").textContent=`🖼️ ${f.name}`;});
  document.getElementById("urlForm").addEventListener("submit",e=>{e.preventDefault();const u=document.getElementById("urlInput").value.trim(),fd=new FormData();fd.append("url",u);runScan("/api/scan/url",fd,"url",u);});
  document.getElementById("textForm").addEventListener("submit",e=>{e.preventDefault();const m=document.getElementById("textInput").value.trim(),fd=new FormData();fd.append("message",m);runScan("/api/scan/text",fd,"text",m.slice(0,55));});
  document.getElementById("apkForm").addEventListener("submit",e=>{e.preventDefault();const f=document.getElementById("apkInput").files[0];if(!f)return;const fd=new FormData();fd.append("file",f);runScan("/api/scan/apk",fd,"apk",f.name);});
  document.getElementById("imageForm").addEventListener("submit",e=>{e.preventDefault();const f=document.getElementById("imageInput").files[0];if(!f)return;const fd=new FormData();fd.append("file",f);runScan("/api/scan/image",fd,"image",f.name,"scannerResultMirror");});
  document.getElementById("clearHistoryBtn").addEventListener("click",()=>{localStorage.removeItem(HKEY);renderHistory();});
  if("serviceWorker"in navigator)navigator.serviceWorker.register("/sw.js").catch(()=>{});
  const ib=document.getElementById("installBtn");window.addEventListener("beforeinstallprompt",e=>{e.preventDefault();deferredPrompt=e;ib.classList.remove("hidden");});
  ib.addEventListener("click",async()=>{if(!deferredPrompt)return;deferredPrompt.prompt();await deferredPrompt.userChoice;deferredPrompt=null;ib.classList.add("hidden");});
});
