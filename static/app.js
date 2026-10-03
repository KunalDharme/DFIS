/* DFIS front end: React 18 (UMD), no build step. Backend contract unchanged:
   GET /api/health, POST /api/otp/request, POST /api/otp/verify, WS /ws/scan */
(function(){
const {useState,useEffect,useRef}=React, h=React.createElement;
const colour=r=>r>=70?'var(--bad)':r>=45?'var(--warn)':'var(--ok)';
const level=r=>r>=76?'Critical risk':r>=51?'High risk':r>=26?'Moderate risk':'Low risk';
const post=(u,b)=>fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)}).then(async r=>{const j=await r.json();if(!r.ok)throw new Error(j.detail||'Request failed');return j});

function Header({theme,onTheme,onPremium}){
  return h('header',{className:'hdr'},h('div',{className:'wrap'},
    h('a',{className:'brand',href:'/','aria-label':'DFIS home'},
      h('span',{className:'logo'},h('svg',{viewBox:'0 0 24 24'},h('circle',{cx:11,cy:11,r:6}),h('path',{d:'M16 16l5 5'}))),'DFIS'),
    h('nav',{className:'nav','aria-label':'Primary'},h('a',{href:'#modules'},'Modules'),h('a',{href:'#why'},'Why DFIS')),
    h('span',{className:'sp'}),
    h('span',{className:'live'},h('i'),'System online'),
    h('button',{className:'upgrade',onClick:onPremium,'aria-label':'Upgrade to Pro'},
      h('svg',{viewBox:'0 0 24 24','aria-hidden':true},h('path',{d:'m12 3 2.35 4.76 5.25.76-3.8 3.7.9 5.23L12 15l-4.7 2.45.9-5.23-3.8-3.7 5.25-.76L12 3Z'})),
      h('span',{className:'upgrade-label'},'Upgrade to Pro')),
    h('button',{className:'btn sec sm',onClick:onTheme,'aria-label':theme==='dark'?'Switch to light theme':'Switch to dark theme'},theme==='dark'?'Light mode':'Dark mode')));
}

function ScanForm({onVerified,onCode}){
  const [name,setName]=useState(''),[email,setEmail]=useState(''),[ok,setOk]=useState(false),[code,setCode]=useState('');
  const [step,setStep]=useState(1),[err,setErr]=useState(''),[busy,setBusy]=useState(false);
  const send=async e=>{e.preventDefault();setErr('');setBusy(true);
    try{const j=await post('/api/otp/request',{email});setStep(2);onCode(email,j.dev_code)}catch(x){setErr(x.message)}setBusy(false)};
  const verify=async e=>{e.preventDefault();setErr('');setBusy(true);
    try{const j=await post('/api/otp/verify',{email,code});onVerified(j.token,email,name)}catch(x){setErr(x.message)}setBusy(false)};
  return h('div',{className:'panel'},
    h('div',{className:'steps'},h('b',{className:step===1?'on':''},'1 Email'),h('b',{className:step===2?'on':''},'2 Verify')),
    h('h2',null,step===1?'Start a private scan':'Enter your code'),
    h('p',{className:'sub'},step===1?'Takes less than 30 seconds. Verify your email to generate a personal exposure report. We never publish or sell your data.':'We sent a 6-digit code to '+email+'.'),
    step===1?h('form',{onSubmit:send},
      h('label',{className:'f',htmlFor:'name'},'Full name (optional)'),
      h('input',{className:'in',id:'name',type:'text',autoComplete:'name',value:name,onChange:e=>setName(e.target.value)}),
      h('label',{className:'f',htmlFor:'email'},'Email address'),
      h('input',{className:'in',id:'email',type:'email',required:true,autoComplete:'email',value:email,onChange:e=>setEmail(e.target.value)}),
      h('label',{className:'chk'},h('input',{type:'checkbox',required:true,checked:ok,onChange:e=>setOk(e.target.checked)}),'I own this email address and agree to scan it. DFIS only checks addresses you can verify.'),
      h('button',{className:'btn full',disabled:busy},busy?'Sending…':'Send verification code'))
    :h('form',{onSubmit:verify},
      h('label',{className:'f',htmlFor:'code'},'Verification code'),
      h('input',{className:'in',id:'code',type:'text',inputMode:'numeric',maxLength:6,autoFocus:true,value:code,onChange:e=>setCode(e.target.value)}),
      h('div',{style:{height:16}}),
      h('button',{className:'btn full',disabled:busy},busy?'Verifying…':'Verify and scan')),
    h('div',{className:'err',role:'alert'},err));
}

function Console({logs,chips,modules,running}){
  const ref=useRef();useEffect(()=>{if(ref.current)ref.current.scrollTop=ref.current.scrollHeight},[logs]);
  const ids=modules.length?modules:Object.keys(chips);
  const fin=ids.filter(i=>['done','failed','skipped'].includes(chips[i]?.s)).length, run=ids.filter(i=>chips[i]?.s==='running').length;
  const pct=ids.length?Math.round(fin/ids.length*100):0;
  const label=ids.length&&fin===ids.length?'Scan complete':run?run+' tool'+(run===1?'':'s')+' running in parallel':running?'Starting tools…':'Ready to scan';
  return h('div',{className:'panel cons'},
    h('div',{className:'intro'},h('span',{className:'dot'}),h('div',null,h('strong',null,'Live intelligence console'),h('small',null,'Secure analysis environment')),h('em',null,'ENCRYPTED')),
    h('div',{className:'head'},h('strong',null,label),h('span',null,fin+'/'+ids.length+' tools')),
    h('div',{className:'prog',role:'progressbar','aria-valuenow':pct,'aria-valuemin':0,'aria-valuemax':100},h('b',{style:{width:pct+'%'}})),
    h('div',{className:'chips'},Object.entries(chips).map(([id,c])=>h('span',{key:id,className:'chip','data-s':c.s},id.replace(/_/g,' ')+(c.secs!=null?' · '+c.secs+'s':'')))),
    h('div',{className:'term',ref,role:'log','aria-live':'polite','aria-label':'Live scan output'},
      logs.map((l,i)=>h('div',{key:i,className:'ln '+(l.k||'')},l.t)),h('div',{className:'ln'},h('span',{className:'caret'}))));
}

function Gauge({s}){
  return h('div',{className:'panel gauge'},
    h('svg',{viewBox:'0 0 200 110','aria-hidden':true},
      h('path',{d:'M10 100 A90 90 0 0 1 190 100',fill:'none',stroke:'var(--sunk)',strokeWidth:14,strokeLinecap:'round',pathLength:100}),
      h('path',{d:'M10 100 A90 90 0 0 1 190 100',fill:'none',stroke:colour(s),strokeWidth:14,strokeLinecap:'round',pathLength:100,strokeDasharray:s+' 100'})),
    h('div',{className:'n'},s),h('div',{className:'lv'},level(s)),h('div',{className:'small mute'},'out of 100'));
}

function Results({d,email,name}){
  const a=d.analysis||{},cv=d.coverage||{};
  const [dl,setDl]=useState(null),[st,setSt]=useState({});
  const live=d.partial===true;
  const summary=a.summary||`${d.breaches?.length||0} breach sources and ${d.accounts?.length||0} accounts found so far. The assessment will update as more tools finish.`;
  const steps=a.top_steps||['Keep this panel open while the remaining tools complete.','Treat preliminary findings as incomplete until the scan finishes.'];
  const toolNames={domain_intel:'Domain checks',breach_leakcheck:'Breach checks (LeakCheck)',breach_xposedornot:'Breach checks (XposedOrNot)',maigret:'Username checks (Maigret)',holehe:'Email account checks (Holehe)',stealer_hudsonrock:'Infostealer checks (Hudson Rock)',sherlock:'Username checks (Sherlock)',mailaccess:'Email evidence checks (MailAccess)'};
  const toolText=Object.entries(cv.tools||{}).map(([k,v])=>{
    const state=v.status==='done'?'Completed':v.status==='unknown'?'Could not confirm':v.status==='failed'?'Could not complete':v.status==='skipped'?'Skipped':(v.status||'Not started');
    const details=[v.checked&&`${v.checked} matches confirmed`,v.rate_limited&&`${v.rate_limited} requests blocked`].filter(Boolean).join(' · ');
    return {name:toolNames[k]||k.replace(/_/g,' '),state,details};
  });
  const ba=a.breach_analysis&&a.breach_analysis.length?a.breach_analysis:(d.breaches||[]).map(b=>({source:b.source,what_leaked:b.data.join(', '),impact:'',what_to_do:[]}));
  const actions=a.account_actions||[];
  const rows=[['Breach (SB)',d.SB,.5],['Platform presence (SP)',d.SP,.35],['Domain exposure (SD)',d.SD,.15]];
  return h('section',{className:'res','aria-live':'polite',id:'results'},
    live&&h('div',{className:'panel',style:{borderColor:'var(--accent)',background:'var(--wash)'}},
      h('strong',null,'Live preliminary assessment'),
      h('p',{className:'small mute',style:{marginTop:6}},'Results below update as each intelligence module completes. The final score and account enrichment arrive when the scan is complete.')),
    h('div',{className:'grid2'},h(Gauge,{s:d.S}),
      h('div',{className:'panel'},h('h2',{style:{fontSize:22}},'What this means'),h('p',{style:{marginTop:6}},summary),
        h('h3',{className:'h3',style:{marginTop:18}},'Do this next'),h('ul',{className:'l'},steps.map((x,i)=>h('li',{key:i},x))),
        h('p',{className:'small mute',style:{marginTop:12}},live?'Preliminary rule-based assessment.':' '+(d.llm_used?'Analysis by '+d.llm_used+'. The score itself comes from the paper formula.':'Rule-based analysis (no LLM configured).')))),
    h('div',{className:'panel'},h('h3',{className:'h3'},'Coverage and confidence'),
      h('p',{className:'mute'},`Overall assessment: ${cv.assessment||'inconclusive'}. Confidence: ${Math.round((cv.confidence||0)*100)}%. This describes how much of the scan returned usable evidence; it is not a guarantee that the account is safe.`),
      toolText.length?h('div',{className:'coverage-list'},toolText.map(x=>h('div',{className:'coverage-item',key:x.name},h('span',null,x.name),h('span',{className:x.state==='Completed'?'coverage-ok':'coverage-note'},x.state+(x.details?' · '+x.details:''))))):h('p',{className:'mute'},'No tool coverage recorded.'),
      a.confidence_notes&&h('p',{style:{marginTop:8}},a.confidence_notes)),
    h('div',{className:'panel'},h('h3',{className:'h3'},'How the score is calculated'),
      h('p',{className:'small mute'},'S = 0.50 × SB + 0.35 × SP + 0.15 × SD. The per-account scores below extend the paper’s model.'),
      rows.map(([n,v,w])=>h('div',{className:'row',key:n},h('span',null,n+' × '+w),h('span',{className:'bar'},h('b',{style:{width:v+'%',background:colour(v)}})),h('span',null,v+' → '+(v*w).toFixed(1))))),
    h('div',{className:'panel'},h('h3',{className:'h3'},'Breaches found ',h('span',{className:'breach-count'},'('+ba.length+')')),
      ba.length?ba.map((b,i)=>h('div',{className:'item',key:i},h('h4',null,b.source),h('p',null,'Leaked: '+b.what_leaked),b.impact&&h('p',null,b.impact),
        b.what_to_do&&b.what_to_do.length>0&&h('ul',{className:'l'},b.what_to_do.map((x,j)=>h('li',{key:j},x))))):h('p',{className:'mute'},'No breaches found for this email.')),
    h('div',{className:'panel'},h('h3',{className:'h3'},'Detailed account findings'),
      actions.length?actions.map((x,i)=>h('div',{className:'item',key:i},h('h4',null,x.domain,h('span',{className:'tag'},x.priority||'review')),h('ul',{className:'l'},(x.steps||[]).map((s,j)=>h('li',{key:j},s))))):h('p',{className:'mute'},'No detailed account findings were returned.')),
    h('div',{className:'tw'},h('table',null,h('thead',null,h('tr',null,['Site','Type','Risk','Evidence','Notes','Deletion'].map(t=>h('th',{key:t},t)))),
      h('tbody',null,(d.accounts||[]).map((x,i)=>h('tr',{key:i},
        h('td',null,h('strong',null,x.domain)),h('td',null,x.category),
        h('td',null,h('div',{className:'rk'},h('span',{className:'bar'},h('b',{style:{width:x.risk+'%',background:colour(x.risk)}})),x.risk)),
        h('td',null,h('span',{className:'tag'},x.confidence_label||'possible'),h('div',{className:'small mute'},(x.found_by||[]).join(', '))),
        h('td',null,x.breached&&h('span',{className:'tag bad'},'in a breach'),' ',x.age_years!=null?x.age_years+' yr old domain ':'',x.difficulty||'unknown'),
        h('td',null,h('button',{className:'btn sec sm',onClick:()=>setDl(x)},st[x.domain]||'Delete'))))))),
    dl&&h(DeleteModal,{a:dl,email,name,status:st[dl.domain]||'Not started',steps:(actions.find(z=>z.domain===dl.domain)||{}).steps,
      onStatus:v=>setSt({...st,[dl.domain]:v==='Not started'?'':v}),onClose:()=>setDl(null)}));
}

function DeleteModal({a,email,name,status,steps,onStatus,onClose}){
  const subj=encodeURIComponent('Request to erase my personal data');
  const body=encodeURIComponent(`Hello,\n\nI request erasure of all personal data linked to ${email} under Section 12 of India's Digital Personal Data Protection Act, 2023 (and GDPR Article 17 where it applies). Please confirm once deleted.\n\nThanks,\n${name||''}`);
  const to=a.delete_email||`privacy@${a.domain}`;
  useEffect(()=>{const k=e=>e.key==='Escape'&&onClose();addEventListener('keydown',k);return()=>removeEventListener('keydown',k)},[]);
  return h('div',{className:'modal',onClick:onClose},h('div',{className:'box',role:'dialog','aria-modal':true,onClick:e=>e.stopPropagation()},
    h('h2',null,'Delete your '+a.domain+' account'),
    h('ol',null,
      h('li',null,a.delete_url?[h('a',{key:1,href:a.delete_url,target:'_blank',rel:'noopener'},'Open the deletion page'),' and sign in.']:'No deletion page on record. Use the email below.'),
      h('li',null,'If the site has no delete button, ',h('a',{href:`mailto:${to}?subject=${subj}&body=${body}`},'send a deletion request to '+to),'.'),
      h('li',null,'Change the password anywhere you reused it, then set the status below.')),
    a.notes&&h('p',{className:'mute'},h('em',null,a.notes)),
    steps&&steps.length>0&&[h('h3',{key:'t',className:'h3',style:{marginTop:16}},'Recommended steps'),h('ol',{key:'o'},steps.map((s,i)=>h('li',{key:i},s)))],
    h('label',{className:'f',htmlFor:'st'},'Status'),
    h('select',{id:'st',value:status,onChange:e=>onStatus(e.target.value)},['Not started','Requested','Confirmed deleted'].map(o=>h('option',{key:o},o))),
    h('div',{style:{marginTop:20}},h('button',{className:'btn sec',onClick:onClose},'Close'))));
}

function PremiumPage({onBack}){
  const comparisons=[
    ['Email exposure scan','Core checks','Expanded coverage'],
    ['Username-based search','—','Planned Pro feature'],
    ['Domain intelligence','Essential signals','Pre-visit domain safety'],
    ['Risk assessment','Rule-based score','Deeper evidence correlation'],
    ['Results and guidance','Live dashboard','Priority insights and remediation'],
    ['Scan history and monitoring','—','Planned Pro feature']
  ];
  const benefits=[
    ['✦','Search beyond email','Connect usernames and aliases to a wider public footprint.'],
    ['◈','Check before you visit','Review domain reputation, redirects, certificates, and risk signals first.'],
    ['↗','More intelligence sources','Add carefully researched tools as DFIS Pro coverage grows.'],
    ['✓','Clearer decisions','See evidence, confidence, and practical next steps in one place.']
  ];
  return h('main',{className:'premium-page'},
    h('section',{className:'premium-hero wrap'},
      h('button',{className:'premium-back',onClick:onBack},'← Back to DFIS'),
      h('div',{className:'premium-hero-content'},
        h('div',{className:'premium-badge'},h('span',{className:'premium-icon','aria-hidden':true},'✦'),'DFIS PREMIUM'),
        h('h1',null,'Upgrade your exposure intelligence'),
        h('p',null,'Go beyond a single scan with deeper identity coverage, domain safety signals, and clearer guidance for reducing your digital footprint.'),
        h('div',{className:'premium-hero-actions'},h('button',{className:'btn premium-cta',onClick:onBack},'Preview dashboard'),h('span',null,'Premium preview · Coming soon')))),
    h('section',{className:'wrap premium-section'},h('div',{className:'premium-section-heading'},h('div',null,h('p',{className:'premium-kicker'},'WHY PRO'),h('h2',null,'More context. Better decisions.'),h('p',{className:'mute'},'A planned premium experience designed around trustworthy, explainable intelligence.'))),
      h('div',{className:'premium-benefits'},benefits.map(([icon,title,text])=>h('article',{className:'premium-benefit',key:title},h('span',{className:'benefit-icon','aria-hidden':true},icon),h('h3',null,title),h('p',null,text))))),
    h('section',{className:'wrap premium-section'},h('div',{className:'premium-section-heading'},h('div',null,h('p',{className:'premium-kicker'},'FREE VS PRO'),h('h2',null,'Choose the level of coverage you need'))),
      h('div',{className:'premium-table-wrap'},h('table',{className:'premium-table'},h('thead',null,h('tr',null,h('th',null,'Capability'),h('th',null,'DFIS Free'),h('th',{className:'pro-column'},'DFIS Pro'))),h('tbody',null,comparisons.map(([feature,free,pro])=>h('tr',{key:feature},h('th',null,feature),h('td',null,free),h('td',{className:'pro-column'},h('span',{className:'pro-value'},pro)))))))),
    h('section',{className:'wrap premium-section'},h('div',{className:'premium-price-card'},h('div',null,h('p',{className:'premium-kicker'},'ILLUSTRATIVE EXAMPLE'),h('h2',null,'Premium, made accessible.'),h('p',null,'For demonstration purposes, a future plan could be offered at an example price of only ₹500 per year.'),h('small',null,'This is only a project concept. No payment or subscription is active yet.')),h('div',{className:'premium-price'},h('strong',null,'₹500'),h('span',null,'/ year')))),
    h('section',{className:'wrap premium-note'},h('p',null,'DFIS Pro is planned for a future release. Current scanning, verification, and dashboard features remain available as before.')));
}

function Marketing(){
  const BR=[781,1093,1300,1473,1632,1802,2116,2724,3205,3500,3900],mx=4000;
  const cmp=[['Breach lookup','Y','N','Y'],['Username enumeration','N','Y','Y'],['Platform presence','N','Y','Partial'],['Risk scoring','N','N','N'],['Remediation','N','N','N'],['Unified dashboard','N','N','N'],['Non-technical users','Y','N','N']];
  const m=x=>x==='Y'?'✓':x==='N'?'–':x;
  const mods=[['SB · weight 0.50','Breach Intelligence','Queries HaveIBeenPwned and LeakCheck.io, normalises each breach and weights data types by severity.'],
    ['SP · weight 0.35','Platform Presence','Searches 500+ platforms from the WhatsMyName database with Python asyncio, targeting about 15 seconds per scan.'],
    ['SD · weight 0.15','Domain Intelligence','Uses Shodan and Hunter.io to find subdomains, open services and related emails.']];
  return h('div',null,
    h('section',{id:'modules',className:'sec'},h('h2',null,'Three OSINT modules, run in parallel'),
      h('p',{className:'mute'},'Risk bands: Low 0–25, Moderate 26–50, High 51–75, Critical 76–100.'),
      h('div',{className:'mods'},mods.map(([w,t,p])=>h('div',{className:'panel',key:t},h('div',{className:'w'},w),h('h3',null,t),h('p',null,p))))),
    h('section',{id:'why',className:'sec'},h('h2',null,'Why DFIS'),
      h('p',{className:'mute',style:{marginBottom:20}},'Data breaches keep rising, and existing tools each cover only part of the picture.'),
      h('div',{className:'panel'},
        h('svg',{className:'chart',viewBox:'0 0 440 190',role:'img','aria-label':'Bar chart of data breaches per year from 2015 to 2025'},
          BR.map((v,i)=>{const ht=v/mx*150,x=10+i*39;return h('g',{key:i},
            h('rect',{x,y:165-ht,width:31,height:ht,rx:3,fill:i>=8?'var(--bad)':'var(--accent)'}),
            h('text',{x:x+15.5,y:160-ht,fontSize:8.5,textAnchor:'middle',fill:'currentColor'},v),
            h('text',{x:x+15.5,y:180,fontSize:9,textAnchor:'middle',fill:'currentColor'},2015+i))})),
        h('p',{className:'small mute'},'Data breaches per year, 2015–2025 (2025 estimated). Source: Identity Theft Resource Center, as in the paper.')),
      h('div',{className:'tw cmp',style:{marginTop:20}},h('table',null,h('thead',null,h('tr',null,['Feature','HIBP','Sherlock','Manual OSINT','DFIS'].map(t=>h('th',{key:t},t)))),
        h('tbody',null,cmp.map(([f,a,b,c])=>h('tr',{key:f},h('td',null,f),h('td',null,m(a)),h('td',null,m(b)),h('td',null,m(c)),h('td',null,'✓'))))))));
}

const SOCIAL=[['Facebook','https://www.facebook.com/'],['YouTube','https://www.youtube.com/'],['X','https://x.com/'],['Instagram','https://www.instagram.com/'],['LinkedIn','https://www.linkedin.com/']];
const ICON={"Facebook": "M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z", "YouTube": "M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z", "X": "M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z", "Instagram": "M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z", "LinkedIn": "M19 0h-14c-2.761 0-5 2.239-5 5v14c0 2.761 2.239 5 5 5h14c2.762 0 5-2.239 5-5v-14c0-2.761-2.238-5-5-5zm-11 19h-3v-11h3v11zm-1.5-12.268c-.966 0-1.75-.79-1.75-1.764s.784-1.764 1.75-1.764 1.75.79 1.75 1.764-.783 1.764-1.75 1.764zm13.5 12.268h-3v-5.604c0-3.368-4-3.113-4 0v5.604h-3v-11h3v1.765c1.396-2.586 7-2.777 7 2.476v6.759z"};
function Footer(){
  const links=['Privacy Notice','Cookie Policy','Accessibility Declaration','Disclaimer','Security Policy','Terms of Service'];
  return h('footer',{className:'ftr'},h('div',{className:'wrap'},
    h('div',null,h('strong',{style:{fontSize:18}},'DFIS'),h('small',null,'Digital Footprint Intelligence System')),
    h('div',null,h('div',null,'© '+new Date().getFullYear()+' DFIS, JSPM’s RSCOE.'),h('nav',{'aria-label':'Legal'},links.map(l=>h('a',{key:l,href:'#'+l.split(' ')[0].toLowerCase()},l))),h('a',{className:'cookie',href:'#cookies'},'Customize Cookies →')),
    h('nav',{className:'social','aria-label':'Social media'},SOCIAL.map(([n,u])=>h('a',{key:n,href:u,target:'_blank',rel:'noopener noreferrer','aria-label':'DFIS on '+n},h('svg',{viewBox:'0 0 24 24',width:18,height:18,fill:'currentColor','aria-hidden':true},h('path',{d:ICON[n]})))))));
}

function App(){
  const [theme,setTheme]=useState(document.documentElement.dataset.theme||'light');
  const [logs,setLogs]=useState([]),[chips,setChips]=useState({}),[modules,setModules]=useState([]),[running,setRunning]=useState(false);
  const [result,setResult]=useState(null),[who,setWho]=useState({email:'',name:''});
  const [premiumPage,setPremiumPage]=useState(false);
  const liveResultShown=useRef(false);
  const chipsRef=useRef({});chipsRef.current=chips;
  const log=(t,k='')=>setLogs(l=>[...l,{t,k}]);
  const toggle=()=>{const n=theme==='dark'?'light':'dark';document.documentElement.dataset.theme=n;try{localStorage.setItem('dfis-theme',n)}catch(e){}setTheme(n)};
  useEffect(()=>{
    setLogs([{t:'$ dfis status',k:'cmd'}]);
    fetch('/api/health').then(r=>r.json()).then(hh=>{
      const l=[{t:'$ dfis status',k:'cmd'}];
      Object.entries(hh.tools||{}).forEach(([t,ok])=>l.push({t:'  '+t+': '+(ok?'ready':'not installed'),k:ok?'ok':'warn'}));
      l.push({t:'  llm: '+(hh.llm||'none (rule-based analysis)'),k:hh.llm?'ok':'warn'},{t:'waiting for a verified email'});
      setLogs(l);const c={};(hh.modules||[]).forEach(m=>c[m]={s:'idle'});setChips(c)}).catch(()=>{});
  },[]);
  const onCode=(email,dev)=>{log('verification code sent to '+email,'ok');if(dev)log('[dev mode] your code is '+dev,'warn')};
  const onVerified=(token,email,name)=>{setWho({email,name});setLogs([]);setResult(null);liveResultShown.current=false;setRunning(true);
    const ws=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/ws/scan');
    ws.onopen=()=>{setModules(Object.keys(chipsRef.current));ws.send(JSON.stringify({token}))};
    ws.onmessage=m=>{const d=JSON.parse(m.data);
      if(d.type==='log')log('['+d.module+'] '+d.text,d.kind==='info'?'':d.kind);
      else if(d.type==='status')setChips(c=>({...c,[d.module]:{s:d.state,secs:d.secs}}));
      else if(d.type==='error')log('error: '+d.text,'err');
      else if(d.type==='partial_result'){
        setResult(d);
        if(!liveResultShown.current){liveResultShown.current=true;setTimeout(()=>document.getElementById('results')?.scrollIntoView({behavior:'smooth'}),50)}
      }
      else if(d.type==='result'){setResult({...d,partial:false});setTimeout(()=>document.getElementById('results')?.scrollIntoView({behavior:'smooth'}),50)}};
    ws.onclose=()=>{setRunning(false);log('connection closed')};
    ws.onerror=()=>log('could not reach the scan server','err')};
  return h(React.Fragment,null,h(Header,{theme,onTheme:toggle,onPremium:()=>setPremiumPage(true)}),
    premiumPage?h(PremiumPage,{onBack:()=>setPremiumPage(false)}):h(React.Fragment,null,
    h('main',{className:'wrap'},
      h('section',{className:'hero'},
        h('div',null,h('div',{className:'eyebrow'},h('span'),'Privacy intelligence platform'),h('h1',null,'Find the accounts you forgot you made.'),
          h('p',{className:'lede'},'The Digital Footprint Intelligence System is an OSINT-based platform for personal data exposure and risk analysis. It combines breach detection, platform presence, risk scoring and fix-it advice in one dashboard.'),
          h(ScanForm,{onVerified,onCode}),
          h('div',{className:'facts'},h('span',null,'500+ platforms'),h('span',null,'Private by design'),h('span',null,'Actionable reports'))),
        h(Console,{logs,chips,modules,running})),
      result&&h(Results,{d:result,email:who.email,name:who.name}),
      h(Marketing)),
    h(Footer)));
}
ReactDOM.createRoot(document.getElementById('root')).render(h(App));
})();