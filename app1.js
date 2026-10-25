const DEPTS=["Computer Science","Electrical Eng.","Mechanical Eng.","Data Science"];
const CATS=["Lab Equipment","Computing Cluster","Software License","Research Kit"];
const sync=(p,onOk)=>p.then(onOk||(()=>{})).catch(err=>toast("Server error: "+err.message,"err"));
const $=id=>document.getElementById(id);
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const today=()=>new Date().toISOString().slice(0,10);
let S={faculty:[],resources:[],logs:[]}, undoSnap=null, proposal=null, tab='input', charts={}, bookingRes=null;

/* ---------- storage (survives refresh) ---------- */
function save(){API.saveLocal(S)}

function loadSample(){
 S={faculty:[
  {id:1,name:"Dr. Sarah Jenkins",department:"Computer Science",maxCapacity:40,expertise:"AI, Machine Learning",tasks:[{id:101,title:"CS101 Intro to AI",hours:15,type:"Lecture"},{id:102,title:"CS402 Deep Learning Lab",hours:18,type:"Lab Duty"},{id:103,title:"Department Research",hours:12,type:"Research"}]},
  {id:2,name:"Prof. Michael Chen",department:"Computer Science",maxCapacity:40,expertise:"Data Structures, Python",tasks:[{id:104,title:"CS201 Data Structures",hours:12,type:"Lecture"}]},
  {id:3,name:"Dr. Elena Rostova",department:"Electrical Eng.",maxCapacity:38,expertise:"Embedded Systems, IoT",tasks:[{id:105,title:"EE301 Embedded Circuits",hours:16,type:"Lecture"},{id:106,title:"EE-Lab Supervision",hours:14,type:"Lab Duty"}]}],
 resources:[
  {id:1,name:"NVIDIA H100 GPU Cluster",category:"Computing Cluster",department:"Computer Science",bookings:[]},
  {id:2,name:"Digital Oscilloscope Rig",category:"Lab Equipment",department:"Electrical Eng.",bookings:[]},
  {id:3,name:"Ansys Simulation License",category:"Software License",department:"Mechanical Eng.",bookings:[{id:1,by:"Dr. Elena Rostova",date:today(),slot:"09:00-11:00"}]}],
 logs:[]};
 S.timetable=[{id:1,fid:1,day:"Mon",slot:"09:00-11:00",title:"CS101 Intro to AI"},{id:2,fid:1,day:"Wed",slot:"11:00-13:00",title:"CS402 DL Lab"},{id:3,fid:2,day:"Tue",slot:"14:00-16:00",title:"CS201 Data Structures"},{id:4,fid:3,day:"Mon",slot:"09:00-11:00",title:"EE301 Embedded Circuits"}];S.covers=[];S.notes=[];
 undoSnap=null;proposal=null;render();toast("Sample data loaded");
}
function clearAll(){if(!confirm("Delete all faculty, tasks and resources?"))return;S={faculty:[],resources:[],logs:[]};undoSnap=null;proposal=null;render();toast("All data cleared","warn")}

/* ---------- helpers ---------- */
const hrs=f=>f.tasks.reduce((s,t)=>s+(+t.hours),0);
function status(f){const h=hrs(f);
 if(h>f.maxCapacity)return{label:"Overloaded",c:"bg-rose-500/20 text-rose-400 border-rose-500/30"};
 if(h<f.maxCapacity-10)return{label:"Underutilized",c:"bg-amber-500/20 text-amber-400 border-amber-500/30"};
 return{label:"Optimal",c:"bg-emerald-500/20 text-emerald-400 border-emerald-500/30"}}
const resStatus=r=>r.bookings.length?"Booked":"Available";
const resBadge=r=>resStatus(r)==="Available"?'bg-emerald-900/40 text-emerald-300 border border-emerald-700':'bg-amber-900/40 text-amber-300 border border-amber-700';
const log=m=>{S.logs.unshift(`[${new Date().toLocaleString()}] ${m}`);S.logs=S.logs.slice(0,30);sync(API.addLog(m))};
function toast(msg,type="ok"){const d=document.createElement("div");
 d.className=`px-4 py-2 rounded-lg text-sm shadow-lg border ${type==="warn"?"bg-amber-900/90 border-amber-700 text-amber-100":type==="err"?"bg-rose-900/90 border-rose-700 text-rose-100":"bg-slate-800 border-slate-600 text-slate-100"}`;
 d.textContent=msg;$("toasts").appendChild(d);setTimeout(()=>d.remove(),3000)}

/* ---------- actions ---------- */
function addFaculty(e){e.preventDefault();
 const nf={id:Date.now(),name:$("f-name").value.trim(),department:$("f-dept").value,maxCapacity:+$("f-max").value,expertise:$("f-skills").value.trim(),tasks:[]};
 S.faculty.push(nf);sync(API.addFaculty(nf),r=>{if(r&&r.id!=null){nf.id=r.id;render()}});
 e.target.reset();render();toast("Faculty added")}
function addTask(e){e.preventDefault();
 const f=S.faculty.find(x=>x.id==$("t-faculty").value);if(!f)return toast("Add a faculty member first","err");
 const nt={id:Date.now(),title:$("t-title").value.trim(),type:$("t-type").value,hours:+$("t-hours").value};
 f.tasks.push(nt);sync(API.addTask(f.id,nt),r=>{if(r&&r.id!=null){nt.id=r.id;render()}});
 if(hrs(f)>f.maxCapacity)notify("mgr",`${f.name} is now overloaded (${hrs(f)}/${f.maxCapacity}h).`);
 e.target.reset();render();toast(hrs(f)>f.maxCapacity?`${f.name} is now overloaded`:"Task added",hrs(f)>f.maxCapacity?"warn":"ok")}
function addResource(e){e.preventDefault();
 const nr={id:Date.now(),name:$("r-name").value.trim(),category:$("r-cat").value,department:$("r-dept").value,bookings:[]};
 S.resources.push(nr);sync(API.addResource(nr),r=>{if(r&&r.id!=null){nr.id=r.id;render()}});
 e.target.reset();render();toast("Resource added")}
function removeFaculty(id){sync(API.removeFaculty(id));S.faculty=S.faculty.filter(f=>f.id!==id);S.timetable=(S.timetable||[]).filter(t=>t.fid!==id);S.covers=(S.covers||[]).filter(c=>c.fromId!==id&&c.toId!==id&&S.timetable.some(t=>t.id===c.slotId));render()}
function removeResource(id){sync(API.removeResource(id));S.resources=S.resources.filter(r=>r.id!==id);render()}
function removeTask(fid,tid){sync(API.removeTask(fid,tid));const f=S.faculty.find(x=>x.id===fid);if(f)f.tasks=f.tasks.filter(t=>t.id!==tid);render()}

/* ---------- optimizer (preview -> apply -> undo) ---------- */
function previewOptimize(){
 const cross=$("cross").checked,load={};S.faculty.forEach(f=>load[f.id]=hrs(f));
 const moves=[];
 S.faculty.forEach(o=>{[...o.tasks].reverse().forEach(t=>{
  if(load[o.id]<=o.maxCapacity)return;
  const c=S.faculty.filter(f=>f.id!==o.id&&(cross||f.department===o.department)&&load[f.id]+t.hours<=f.maxCapacity)
   .sort((a,b)=>load[a.id]/a.maxCapacity-load[b.id]/b.maxCapacity)[0];
  if(c){load[o.id]-=t.hours;load[c.id]+=t.hours;moves.push({tid:t.id,title:t.title,hours:t.hours,from:o.id,to:c.id})}
 })});
 proposal=moves;renderProposal();
 if(!moves.length)toast("Nothing to rebalance","warn")}
function renderProposal(){
 const el=$("proposal");
 if(!proposal){el.classList.add("hidden");return}
 el.classList.remove("hidden");
 const nm=id=>esc(S.faculty.find(f=>f.id===id)?.name||"?");
 el.innerHTML=proposal.length?`<div class="border border-indigo-500/30 rounded-lg p-4 bg-slate-900/60 space-y-2">
  <p class="text-sm font-semibold text-indigo-300">${proposal.length} suggested move(s)</p>
  ${proposal.map(m=>`<p class="text-xs text-slate-300"><i class="fa-solid fa-arrow-right text-indigo-400 mr-1"></i>"${esc(m.title)}" (${m.hours}h): ${nm(m.from)} → ${nm(m.to)}</p>`).join("")}
  <div class="flex gap-2 pt-2"><button onclick="applyOptimize()" class="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 rounded text-xs font-semibold">Apply</button>
  <button onclick="proposal=null;renderProposal()" class="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 rounded text-xs">Dismiss</button></div></div>`
 :`<p class="text-xs text-slate-400 border border-slate-700 rounded-lg p-3">No overloaded faculty, or no colleague has enough spare capacity.</p>`}
function applyOptimize(){
 undoSnap=JSON.stringify(S.faculty);sync(API.applyOptimization(proposal));
 proposal.forEach(m=>{const o=S.faculty.find(f=>f.id===m.from),c=S.faculty.find(f=>f.id===m.to);
  const i=o.tasks.findIndex(t=>t.id===m.tid);if(i>-1){c.tasks.push(o.tasks.splice(i,1)[0]);notify(c.id,`"${m.title}" was reassigned to you by the optimizer.`)}});
 log(`Optimizer reallocated ${proposal.length} task(s)`);toast(`${proposal.length} task(s) reallocated`);
 proposal=null;render()}
function undoOptimize(){if(!undoSnap)return;sync(API.undoOptimization());S.faculty=JSON.parse(undoSnap);undoSnap=null;log("Optimizer changes undone");render();toast("Undone")}

/* ---------- booking ---------- */
function openBooking(id){bookingRes=S.resources.find(r=>r.id===id);
 if(!S.faculty.length)return toast("Add a faculty member first","err");
 $("m-title").textContent="Request: "+bookingRes.name;
 $("m-fac").innerHTML=S.faculty.map(f=>`<option>${esc(f.name)}</option>`).join("");
 $("m-date").min=today();$("m-date").value=today();$("modal").classList.remove("hidden")}
function closeModal(){$("modal").classList.add("hidden")}
function confirmBooking(e){e.preventDefault();
 const b={id:Date.now(),by:$("m-fac").value,date:$("m-date").value,slot:$("m-slot").value};
 const clash=bookingRes.bookings.find(x=>x.date===b.date&&x.slot===b.slot);
 if(clash)return toast(`Clash: already booked by ${clash.by} for that slot`,"err");
 bookingRes.bookings.push(b);sync(API.addBooking(bookingRes.id,b),r=>{if(r&&r.id!=null){b.id=r.id;render()}});log(`${b.by} booked "${bookingRes.name}" on ${b.date} (${b.slot})`);
 closeModal();render();toast("Booking confirmed")}
function cancelBooking(rid,bid){sync(API.removeBooking(rid,bid));const r=S.resources.find(x=>x.id===rid);
 const b=r.bookings.find(x=>x.id===bid);r.bookings=r.bookings.filter(x=>x.id!==bid);
 log(`Booking of "${r.name}" by ${b.by} (${b.date}) was released`);render()}

/* ---------- export ---------- */
function exportCSV(){
 const rows=[["Name","Department","Max Hours","Assigned Hours","Status","Tasks"]];
 S.faculty.forEach(f=>rows.push([f.name,f.department,f.maxCapacity,hrs(f),status(f).label,f.tasks.map(t=>`${t.title} (${t.hours}h)`).join("; ")]));
 const csv=rows.map(r=>r.map(v=>`"${String(v).replace(/"/g,'""')}"`).join(",")).join("\n");
 const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([csv],{type:"text/csv"}));a.download="workload-report.csv";a.click();toast("Report exported")}

/* ---------- rendering ---------- */
function switchTab(t){tab=t;
 ["input","optimizer","resources","timetable"].forEach(x=>{
  $("tab-"+x).className="px-4 py-2 rounded-lg font-medium text-sm transition flex items-center gap-2 "+(x===t?"bg-indigo-600 text-white":"bg-slate-800 text-slate-400 hover:text-white");
  $("sec-"+x).classList.toggle("hidden",x!==t)});
 if(t==="optimizer")renderCharts()}

function render(){
 norm();
 document.querySelectorAll(".dept-sel").forEach(s=>{if(!s.options.length)s.innerHTML=DEPTS.map(d=>`<option>${d}</option>`).join("")});
 document.querySelectorAll(".cat-sel").forEach(s=>{if(!s.options.length)s.innerHTML=CATS.map(d=>`<option>${d}</option>`).join("")});
 const fc=$("f-cat");if(!fc.options.length)fc.innerHTML='<option value="">All categories</option>'+CATS.map(d=>`<option>${d}</option>`).join("");
 const sel=$("t-faculty"),prev=sel.value;
 sel.innerHTML=S.faculty.map(f=>`<option value="${f.id}">${esc(f.name)} (${esc(f.department)})</option>`).join("");if(prev)sel.value=prev;

 // KPIs
 const over=S.faculty.filter(f=>hrs(f)>f.maxCapacity).length,tot=S.faculty.reduce((a,f)=>a+hrs(f),0),cap=S.faculty.reduce((a,f)=>a+f.maxCapacity,0);
 const kp=(i,l,v,c)=>`<div class="glass-card p-4 rounded-xl flex items-center gap-3"><i class="fa-solid ${i} text-xl ${c}"></i><div><p class="text-xs text-slate-400">${l}</p><p class="text-lg font-bold">${v}</p></div></div>`;
 $("kpis").innerHTML=kp("fa-users","Faculty",S.faculty.length,"text-indigo-400")+kp("fa-gauge-high","Utilization",cap?Math.round(tot/cap*100)+"%":"0%","text-purple-400")
  +kp("fa-triangle-exclamation","Overloaded",over,over?"text-rose-400":"text-emerald-400")+kp("fa-cube","Resources Free",S.resources.filter(r=>!r.bookings.length).length+"/"+S.resources.length,"text-emerald-400");

 // faculty table (searchable)
 const q=$("q-fac").value.toLowerCase();
 const fl=S.faculty.filter(f=>(f.name+f.department+f.expertise).toLowerCase().includes(q));
 $("fac-badge").textContent=`${S.faculty.length} Faculty`;
 $("fac-body").innerHTML=fl.map(f=>{const h=hrs(f),st=status(f);return`<tr>
  <td class="p-2 font-medium text-white">${esc(f.name)}<div class="text-[10px] text-slate-500">${esc(f.expertise)}</div></td>
  <td class="p-2 text-slate-400">${esc(f.department)}</td>
  <td class="p-2"><span class="font-bold ${h>f.maxCapacity?"text-rose-400":"text-slate-200"}">${h}</span> / ${f.maxCapacity}</td>
  <td class="p-2"><span class="px-2 py-0.5 rounded text-[10px] border ${st.c}">${st.label}</span></td>
  <td class="p-2 text-right"><button onclick="removeFaculty(${f.id})" class="text-rose-400 hover:text-rose-300"><i class="fa-solid fa-trash"></i></button></td></tr>`}).join("")
  ||'<tr><td colspan="5" class="p-3 text-center text-slate-500">No faculty found.</td></tr>';

 // resource table
 $("res-badge").textContent=`${S.resources.length} Items`;
 $("res-body").innerHTML=S.resources.map(r=>`<tr><td class="p-2 font-medium text-white">${esc(r.name)}</td><td class="p-2 text-slate-400">${esc(r.category)}</td><td class="p-2 text-slate-400">${esc(r.department)}</td>
  <td class="p-2"><span class="px-2 py-0.5 rounded text-[10px] ${resBadge(r)}">${resStatus(r)}</span></td>
  <td class="p-2 text-right"><button onclick="removeResource(${r.id})" class="text-rose-400 hover:text-rose-300"><i class="fa-solid fa-trash"></i></button></td></tr>`).join("")
  ||'<tr><td colspan="5" class="p-3 text-center text-slate-500">No resources registered.</td></tr>';

 // optimizer cards (filterable)
 const sf=$("f-status").value;
 $("cards").innerHTML=S.faculty.filter(f=>!sf||status(f).label===sf).map(f=>{
  const h=hrs(f),st=status(f),pct=Math.min(Math.round(h/f.maxCapacity*100),100);
  return`<div class="glass-card p-4 rounded-xl space-y-3">
   <div class="flex items-start justify-between"><div><h4 class="font-bold text-sm">${esc(f.name)}</h4><p class="text-xs text-slate-400">${esc(f.department)}</p></div>
   <span class="text-[10px] font-semibold px-2 py-0.5 rounded border ${st.c}">${st.label}</span></div>
   <div><div class="flex justify-between text-xs mb-1"><span class="text-slate-400">Capacity Usage</span><span class="font-medium">${h} / ${f.maxCapacity} hrs (${pct}%)</span></div>
   <div class="w-full bg-slate-800 h-2 rounded-full overflow-hidden"><div class="h-full ${h>f.maxCapacity?"bg-rose-500":h<f.maxCapacity-10?"bg-amber-500":"bg-emerald-500"}" style="width:${pct}%"></div></div></div>
   <div class="space-y-1.5 pt-2 border-t border-slate-800"><span class="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block">Assigned Tasks</span>
   ${f.tasks.map(t=>`<div class="flex items-center justify-between bg-slate-900/60 p-1.5 rounded text-xs border border-slate-800"><div><p class="font-medium text-slate-200">${esc(t.title)}</p><span class="text-[10px] text-slate-400">${esc(t.type)}</span></div>
   <div class="flex items-center gap-2"><span class="text-indigo-400 font-semibold">${t.hours}h</span><button onclick="removeTask(${f.id},${t.id})" class="text-slate-500 hover:text-rose-400"><i class="fa-solid fa-xmark"></i></button></div></div>`).join("")||'<p class="text-xs text-slate-500 italic">No tasks assigned.</p>'}</div></div>`}).join("");
 $("metrics").innerHTML=`<div class="bg-slate-900/80 p-2 rounded-lg border border-slate-800 flex justify-between text-xs"><span class="text-slate-400">Total Hours</span><b>${tot} / ${cap}</b></div>
  <div class="bg-slate-900/80 p-2 rounded-lg border border-slate-800 flex justify-between text-xs"><span class="text-slate-400">Overloaded</span><b class="${over?"text-rose-400":"text-emerald-400"}">${over}</b></div>`;
 $("undo-btn").classList.toggle("hidden",!undoSnap);

 // resource cards (searchable + filters)
 const rq=$("q-res").value.toLowerCase(),rc=$("f-cat").value,ra=$("f-avail").value;
 $("res-grid").innerHTML=S.resources.filter(r=>(r.name+r.department).toLowerCase().includes(rq)&&(!rc||r.category===rc)&&(!ra||resStatus(r)===ra)).map(r=>`
  <div class="glass-card p-4 rounded-xl space-y-3 flex flex-col justify-between"><div>
   <div class="flex items-start justify-between gap-2"><h4 class="font-bold text-sm">${esc(r.name)}</h4><span class="text-[10px] font-semibold px-2 py-0.5 rounded ${resBadge(r)}">${resStatus(r)}</span></div>
   <p class="text-xs text-slate-400 mt-1"><i class="fa-solid fa-layer-group text-slate-500 mr-1"></i>${esc(r.category)}</p>
   <p class="text-xs text-slate-400"><i class="fa-solid fa-building text-slate-500 mr-1"></i>Dept: ${esc(r.department)}</p>
   ${r.bookings.map(b=>`<div class="flex justify-between items-center text-xs text-amber-400 mt-2"><span><i class="fa-solid fa-user-lock mr-1"></i>${esc(b.by)} · ${b.date} · ${b.slot}</span><button onclick="cancelBooking(${r.id},${b.id})" class="text-slate-500 hover:text-rose-400" title="Release"><i class="fa-solid fa-xmark"></i></button></div>`).join("")}</div>
   <button onclick="openBooking(${r.id})" class="w-full py-2 rounded text-xs font-semibold bg-emerald-600 hover:bg-emerald-500"><i class="fa-solid fa-calendar-plus mr-1"></i> Request Access</button></div>`).join("")
  ||'<p class="text-slate-500 text-xs italic">No resources match.</p>';
 $("logs").innerHTML=S.logs.map(l=>`<li class="border-b border-slate-800/50 pb-1">${esc(l)}</li>`).join("")||'<li class="italic text-slate-500">No bookings yet. Click "Request Access" on any resource.</li>';

 renderProposal();renderTT();renderBell();save();if(tab==="optimizer")renderCharts()}

function renderCharts(){
 Object.values(charts).forEach(c=>c.destroy());
 const tick={color:"#94a3b8"};
 charts.bar=new Chart($("barChart"),{type:"bar",data:{labels:S.faculty.map(f=>f.name),datasets:[
  {label:"Assigned Hours",data:S.faculty.map(hrs),backgroundColor:"rgba(99,102,241,.8)",borderRadius:4},
  {label:"Max Capacity",data:S.faculty.map(f=>f.maxCapacity),backgroundColor:"rgba(148,163,184,.3)",borderRadius:4}]},
  options:{responsive:true,maintainAspectRatio:false,scales:{y:{beginAtZero:true,grid:{color:"rgba(255,255,255,.05)"},ticks:tick},x:{grid:{display:false},ticks:tick}},plugins:{legend:{labels:{color:"#cbd5e1"}}}}});
 const byDept={};S.faculty.forEach(f=>byDept[f.department]=(byDept[f.department]||0)+hrs(f));
 charts.pie=new Chart($("pieChart"),{type:"doughnut",data:{labels:Object.keys(byDept),datasets:[{data:Object.values(byDept),backgroundColor:["#6366f1","#a855f7","#10b981","#f59e0b"],borderWidth:0}]},
  options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:"right",labels:{color:"#cbd5e1",boxWidth:10,font:{size:10}}}}}});
}

/* ---------- roles, timetable, cover requests, notifications ---------- */
const DAYS=["Mon","Tue","Wed","Thu","Fri"],SLOTS=["09:00-11:00","11:00-13:00","14:00-16:00","16:00-18:00"];
let me=null,coverSlot=null;
function norm(){S.timetable=S.timetable||[];S.covers=S.covers||[];S.notes=S.notes||[]}
const fname=id=>esc(S.faculty.find(f=>f.id===id)?.name||"Unknown");
function notify(to,text){norm();S.notes.unshift({id:Date.now()+Math.random(),to,text,read:false,ts:new Date().toLocaleString()});S.notes=S.notes.slice(0,50);sync(API.addNotification(S.notes[0]))}
const mine=()=>(S.notes||[]).filter(n=>me&&(me.role==="faculty"?n.to===me.fid:n.to==="mgr"));

function showLogin(){$("l-fac").innerHTML=S.faculty.map(f=>`<option value="${f.id}">${esc(f.name)}</option>`).join("");onRoleChange();$("login").classList.remove("hidden")}
function onRoleChange(){$("l-fac-wrap").classList.toggle("hidden",$("l-role").value!=="faculty")}
function doLogin(e){e.preventDefault();const role=$("l-role").value;
 if(role==="faculty"&&!S.faculty.length)return toast("No faculty yet. Sign in as Admin first","err");
 me={role,fid:role==="faculty"?+$("l-fac").value:null};
 try{sessionStorage.setItem("frwo-me",JSON.stringify(me))}catch(x){}
 sync(API.login(me));
 $("login").classList.add("hidden");$("tt-fac").value="";applyRole();render()}
function logout(){sync(API.logout());me=null;try{sessionStorage.removeItem("frwo-me")}catch(x){}applyRole();showLogin()}
function applyRole(){const r=me?.role||"";document.body.dataset.role=r;
 const hide=(el,v)=>el&&el.classList.toggle("hidden",v);
 hide($("btn-sample"),r!=="admin");hide($("btn-clear"),r!=="admin");
 hide($("form-faculty").closest(".glass-card"),r!=="admin");
 [$("form-task"),$("form-resource"),$("proposal"),$("form-slot")].forEach(el=>hide(el.closest(".glass-card"),r==="faculty"));
 $("who").textContent=me?(r==="faculty"?(S.faculty.find(f=>f.id===me.fid)?.name||"Faculty"):r.toUpperCase()):""}

function addSlot(e){e.preventDefault();const fid=+$("s-fac").value,day=$("s-day").value,slot=$("s-slot").value;
 if(S.timetable.some(t=>t.fid===fid&&t.day===day&&t.slot===slot))return toast("Clash: this faculty already has a class then","err");
 const ns={id:Date.now(),fid,day,slot,title:$("s-title").value.trim()};
 S.timetable.push(ns);sync(API.addSlot(ns),r=>{if(r&&r.id!=null){ns.id=r.id;render()}});e.target.reset();render();toast("Slot added")}
function delSlot(id){sync(API.removeSlot(id));S.timetable=S.timetable.filter(t=>t.id!==id);S.covers=S.covers.filter(c=>c.slotId!==id);render()}
function openCover(id){coverSlot=S.timetable.find(t=>t.id===id);
 const free=S.faculty.filter(f=>f.id!==coverSlot.fid&&!S.timetable.some(t=>t.fid===f.id&&t.day===coverSlot.day&&t.slot===coverSlot.slot));
 if(!free.length)return toast("No colleague is free at that time","warn");
 $("c-title").textContent=`Cover: ${coverSlot.title} (${coverSlot.day} ${coverSlot.slot})`;
 $("c-sub").innerHTML=free.map(f=>`<option value="${f.id}">${esc(f.name)}</option>`).join("");$("cmodal").classList.remove("hidden")}
function sendCover(e){e.preventDefault();const toId=+$("c-sub").value,t=coverSlot;
 const nc={id:Date.now(),slotId:t.id,fromId:t.fid,toId,why:$("c-why").value.trim(),status:"Pending"};
 S.covers.push(nc);sync(API.addCover(nc),r=>{if(r&&r.id!=null){nc.id=r.id;render()}});
 const from=S.faculty.find(f=>f.id===t.fid)?.name;
 notify(toId,`${from} asks you to cover "${t.title}" (${t.day} ${t.slot}).`);
 notify("mgr",`Cover requested by ${from} for "${t.title}" (${t.day} ${t.slot}).`);
 $("cmodal").classList.add("hidden");$("c-why").value="";render();toast("Cover request sent")}
function answerCover(id,ok){const c=S.covers.find(x=>x.id===id),t=S.timetable.find(x=>x.id===c.slotId);
 c.status=ok?"Accepted":"Declined";sync(API.answerCover(id,c.status));const sub=S.faculty.find(f=>f.id===c.toId)?.name;
 notify(c.fromId,`${sub} ${ok?"accepted":"declined"} your cover request for "${t?.title}".`);
 notify("mgr",`${sub} ${ok?"accepted":"declined"} cover for "${t?.title}".`);render();toast(ok?"Cover accepted":"Cover declined")}

function renderTT(){
 const sf=$("s-fac"),tf=$("tt-fac"),ps=sf.value,pt=tf.value;
 const opts=S.faculty.map(f=>`<option value="${f.id}">${esc(f.name)}</option>`).join("");
 sf.innerHTML=opts;tf.innerHTML=opts;if(ps)sf.value=ps;
 if(pt)tf.value=pt;else if(me?.role==="faculty")tf.value=me.fid;
 const ss=$("s-slot");if(!ss.options.length)ss.innerHTML=SLOTS.map(x=>`<option>${x}</option>`).join("");
 const fid=+tf.value;
 let h=`<thead class="bg-slate-900 text-slate-400"><tr><th class="p-2">Slot</th>${DAYS.map(d=>`<th class="p-2">${d}</th>`).join("")}</tr></thead><tbody>`;
 SLOTS.forEach(sl=>{h+=`<tr><td class="p-2 text-slate-400 whitespace-nowrap">${sl}</td>`;
  DAYS.forEach(d=>{const t=S.timetable.find(x=>x.fid===fid&&x.day===d&&x.slot===sl);
   const cv=t&&S.covers.find(c=>c.slotId===t.id&&c.status!=="Declined");
   const own=!me||me.role!=="faculty"||me.fid===fid;
   h+=`<td class="p-1 h-16 align-top">${t?`<div class="rounded p-1 border ${cv?(cv.status==="Accepted"?"bg-emerald-900/40 border-emerald-700":"bg-amber-900/40 border-amber-700"):"bg-sky-900/40 border-sky-700"}"><p class="font-medium text-slate-100">${esc(t.title)}</p>
    ${cv?`<p class="text-[10px] text-slate-300">${cv.status}: ${fname(cv.toId)}</p>`:own?`<button onclick="openCover(${t.id})" class="text-[10px] text-sky-300 hover:underline">Request cover</button>`:""}
    <button onclick="delSlot(${t.id})" class="mgr-del text-[10px] text-rose-400 ml-1" title="Remove"><i class="fa-solid fa-xmark"></i></button></div>`:""}</td>`});
  h+="</tr>"});
 $("tt-grid").innerHTML=h+"</tbody>";
 $("covers").innerHTML=S.covers.map(c=>{const t=S.timetable.find(x=>x.id===c.slotId);if(!t)return"";
  const can=c.status==="Pending"&&(!me||me.role!=="faculty"||me.fid===c.toId);
  const col=c.status==="Accepted"?"border-emerald-700 text-emerald-300":c.status==="Declined"?"border-rose-700 text-rose-300":"border-amber-700 text-amber-300";
  return`<div class="flex flex-wrap items-center justify-between gap-2 bg-slate-900/60 p-2 rounded border border-slate-800"><span>${esc(t.title)} · ${t.day} ${t.slot}: ${fname(c.fromId)} → ${fname(c.toId)}${c.why?` (${esc(c.why)})`:""}</span>
   <span class="flex items-center gap-2"><span class="px-2 py-0.5 rounded border text-[10px] ${col}">${c.status}</span>${can?`<button onclick="answerCover(${c.id},true)" class="text-emerald-400 hover:underline">Accept</button><button onclick="answerCover(${c.id},false)" class="text-rose-400 hover:underline">Decline</button>`:""}</span></div>`}).join("")
  ||'<p class="italic text-slate-500">No cover requests yet.</p>'}

function renderBell(){const m=mine(),u=m.filter(n=>!n.read).length,b=$("bell-n");
 b.textContent=u;b.classList.toggle("hidden",!u);
 $("notes").innerHTML=m.map(n=>`<div class="border-b border-slate-800 pb-1 ${n.read?"text-slate-500":"text-slate-200"}">${esc(n.text)}<div class="text-[10px] text-slate-500">${n.ts}</div></div>`).join("")||'<p class="italic text-slate-500">No notifications.</p>'}
function toggleNotes(){const p=$("notes");p.classList.toggle("hidden");
 if(!p.classList.contains("hidden")){const m=mine();m.forEach(n=>n.read=true);sync(API.markNotificationsRead(m.map(n=>n.id)));save();$("bell-n").classList.add("hidden")}}

/* ---------- boot ---------- */
$("modal").addEventListener("click",e=>{if(e.target.id==="modal")closeModal()});
try{me=JSON.parse(sessionStorage.getItem("frwo-me"))}catch(e){}
API.loadAll().then(d=>{if(d)S=d;else loadSample()})
 .catch(e=>toast("Could not load data: "+e.message,"err"))
 .then(()=>{switchTab("input");render();applyRole();if(!me)showLogin()});
