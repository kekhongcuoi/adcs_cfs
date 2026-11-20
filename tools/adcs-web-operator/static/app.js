/* ADCS / cFS Mission Control — no external JavaScript libraries */
'use strict';
const $ = (selector, root=document) => root.querySelector(selector);
const $$ = (selector, root=document) => [...root.querySelectorAll(selector)];
const esc = value => String(value??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const F = (num,d=2) => typeof num==='number' && Number.isFinite(num) ? num.toFixed(d) : '—';
const DEG=180/Math.PI;
const niceTime = value => {try{return new Date(value).toLocaleTimeString('vi-VN',{hour12:false,timeZone:'UTC'});}catch{return '—'}};
const color = {imu_app:'#a6e3a1',light_app:'#f3c98b',act_app:'#83bafa',adcs_app:'#c5a2fa',camera_app:'#f48dac'};
const names = {overview:'TỔNG QUAN',apps:'ỨNG DỤNG CFS',commands:'ĐIỀU KHIỂN',telemetry:'TELEMETRY',events:'SỰ KIỆN',settings:'CẤU HÌNH'};
const info = {imu_app:'MPU6050 / GYRO Z',light_app:'SUN SENSOR',act_app:'REACTION WHEEL',adcs_app:'ATTITUDE CONTROL',camera_app:'CAMERA'};
let catalog=[], S=null, page='overview', cmdApp='act_app', cmdName='SET_WHEEL_SPEED', tlmApp='imu_app', eventFilter='ALL', refreshTimer=null, showMobile=false;
// Target Z is an operator reference only; it is never included in an API command.
const TARGET_STORAGE_KEY='adcs.operator.target_z.deg';
const clampTarget=value=>Number.isFinite(value)?Math.round(Math.min(180,Math.max(-180,value))*10)/10:0;
function loadTarget(){try{return clampTarget(Number(window.localStorage.getItem(TARGET_STORAGE_KEY)||0))}catch{return 0}}
let targetZ=loadTarget();
const wrapAngle=value=>((value+180)%360+360)%360-180;
function setTarget(value){
  targetZ=clampTarget(Number(value));
  try{window.localStorage.setItem(TARGET_STORAGE_KEY,String(targetZ))}catch{}
  const number=$('#targetZInput'), slider=$('#targetZSlider');
  if(number&&Number(number.value)!==targetZ)number.value=String(targetZ);
  if(slider&&Number(slider.value)!==targetZ)slider.value=String(targetZ);
  updateTargetReference();
}
function updateTargetReference(){
  const i=S?.telemetry?.imu_app||{};
  const value=$('#targetZValue');if(value)value.textContent=(targetZ>=0?'+':'')+F(targetZ,1)+'°';
  const valid=healthy('imu_app')&&Number(i.valid)===1&&Number(i.status)===0&&
    (S?.mode!=='live'||Number(i.simulated)===0)&&typeof i.angle_rad==='number'&&Number.isFinite(i.angle_rad);
  const error=$('#targetZError'), note=$('#targetZNote'), pointer=$('#targetMarker');
  if(error)error.textContent=valid?((wrapAngle(targetZ-i.angle_rad*DEG)>=0?'+':'')+F(wrapAngle(targetZ-i.angle_rad*DEG),1)+'°'):'—';
  if(note)note.textContent=valid?'Sai lệch ngắn nhất theo trục Z • chỉ hiển thị':'Chưa có góc IMU mới và hợp lệ';
  if(pointer)pointer.style.transform='rotate('+targetZ+'deg)';
}


async function api(path, method='GET',data=null){
  const opts={method,headers:{}};
  if(data!==null){opts.headers['Content-Type']='application/json';opts.body=JSON.stringify(data);}
  const r=await fetch(path,opts);
  let body;
  try{body=await r.json()}catch{throw Error(`Lỗi máy chủ: HTTP ${r.status}`)}
  if(!r.ok)throw Error(body.error||`HTTP ${r.status}`);
  return body;
}
function toast(message,error=false){
  const host=$('#toastHost'), el=document.createElement('div');el.className='toast'+(error?' error':'');el.textContent=message;host.appendChild(el);setTimeout(()=>el.remove(),4700);
}
function utcTick(){ $('#utcClock').textContent = new Date().toISOString().slice(11,19)+' UTC'; }
function iconFor(app){return ({imu_app:'IM',light_app:'LT',act_app:'AC',adcs_app:'AD',camera_app:'CM'})[app]||'CF'}
const appBy = id => catalog.find(a=>a.id===id);
const present = (id) => S?.apps?.[id]?.last_seen;
const healthy = (id) => {
  if(!present(id))return false;
  return Date.now() - Date.parse(S.apps[id].last_seen) < 4500;
};
function statusChip(id){const fresh=healthy(id);return `<span class="app-health"><span class="health-dot ${fresh?'':'off'}"></span>${fresh?'RECEIVING':'NO DATA'}</span>`}
function heading(title,desc,num,extra=''){
  return `<div class="page-heading"><div><div class="eyebrow">GROUND SEGMENT / ${num}</div><h1>${title}</h1><p>${desc}</p></div>${extra?`<div class="page-actions">${extra}</div>`:''}</div>`;
}
function cardHead(title,meta=''){
 return `<div class="card-heading"><h2>${title}</h2>${meta}</div>`;
}
function simTag(){return S?.mode==='simulation'?'SIM DATA':S?.mode==='replay'?'REPLAY DATA':'LIVE INPUT'}
function exportLinks(){return `<button class="btn btn-ghost btn-sm" data-action="export-json">↓ Export JSON</button><a class="btn btn-primary btn-sm" href="/api/export.csv" download>↓ Export CSV</a>`}
function renderOverview(){
  return heading('Tổng quan ADCS','Giám sát IMU, bánh đà và cảm biến ánh sáng trên cùng một màn hình.','01 · MISSION OVERVIEW',`<button class="btn btn-ghost" data-page="settings">⚙ Kết nối</button><button class="btn btn-primary" data-page="commands">⌘ Điều khiển <span>↗</span></button>`)+`
  <div class="grid4">
    <div class="card stat-card"><div class="stat-kicker">TỐC ĐỘ GÓC IMU <span class="stat-symbol">⌁</span></div><div class="stat-value stat-accent"><span data-bind="imuRate">—</span> <span class="stat-unit">°/s</span></div><div class="stat-desc">Gyro Z · tốc độ đã lọc</div></div>
    <div class="card stat-card"><div class="stat-kicker">GÓC TÍCH PHÂN <span class="stat-symbol">◈</span></div><div class="stat-value stat-blue"><span data-bind="imuAngle">—</span> <span class="stat-unit">deg</span></div><div class="stat-desc">Góc tương đối / trục Z</div></div>
    <div class="card stat-card"><div class="stat-kicker">TỐC ĐỘ BÁNH ĐÀ <span class="stat-symbol">◎</span></div><div class="stat-value stat-amber"><span data-bind="wheel">—</span> <span class="stat-unit">rad/s</span></div><div class="stat-desc">WHEEL_DATA · measured/modelled</div></div>
    <div class="card stat-card"><div class="stat-kicker">GÓI TELEMETRY <span class="stat-symbol">↓</span></div><div class="stat-value stat-purple"><span data-bind="packets">—</span></div><div class="stat-desc">Tổng gói thu nhận trong phiên</div></div>
  </div>
  <div class="grid-main section-gap">
    <div class="card card-pad">${cardHead('Tốc độ góc IMU / Angular rate',`<span class="tag" id="rateDataTag">${simTag()}</span>`)}<div class="chart-shell tall"><canvas id="chartRate" aria-label="Biểu đồ tốc độ góc IMU Z theo thời gian"></canvas></div><div class="chart-legend"><span><i class="legend-dot"></i> Gyro Z · rate (°/s)</span><span class="muted">Nguồn: IMU_DATA / 0x08D4</span></div></div>
    <div class="card card-pad">${cardHead('Góc tích phân — 1 trục',`<span class="tag dim">Z AXIS</span>`)}<div class="axis-visual"><div class="radar-ring"></div><div class="radar-cross-h"></div><div class="radar-cross-v"></div><div class="axis-needle" id="axisNeedle"></div><div class="axis-target-needle" id="targetMarker" title="Góc mục tiêu (chỉ tham chiếu)"></div><div class="axis-mid"></div><span class="axis-label axis-top">0°</span><span class="axis-label axis-right">+90°</span><span class="axis-label axis-bottom">±180°</span><span class="axis-label axis-left">−90°</span></div><div class="measure-row"><div><small>Góc đo Z</small><strong id="measureAngle">—</strong><span>độ</span></div><div><small>Bias</small><strong id="measureBias">—</strong><span>°/s</span></div><div><small>IMU hợp lệ</small><strong id="measureValid">—</strong><span>IMU</span></div></div>
      <div class="target-panel" aria-label="Góc Z mục tiêu chỉ dùng làm tham chiếu">
        <div class="target-title"><strong>Góc mục tiêu Z</strong><span class="tag dim">CHỈ THAM CHIẾU</span></div>
        <div class="target-line"><label class="sr-only" for="targetZInput">Góc Z mục tiêu (độ)</label><input id="targetZInput" type="number" min="-180" max="180" step="0.1" value="${targetZ}" aria-label="Góc Z mục tiêu theo độ"><span class="target-unit">°</span><button class="btn btn-ghost btn-sm" type="button" data-action="target-zero">Về 0°</button></div>
        <label class="sr-only" for="targetZSlider">Kéo chọn góc mục tiêu từ âm 180 đến dương 180 độ</label>
        <input class="target-slider" id="targetZSlider" type="range" min="-180" max="180" step="0.1" value="${targetZ}">
        <div class="target-meta"><span>Mục tiêu <b id="targetZValue">—</b></span><span>Độ lệch <b id="targetZError">—</b></span></div>
        <small id="targetZNote" class="muted">Chưa có IMU hợp lệ</small>
        <p class="target-legend"><i></i> Xanh: góc đo IMU <i class="amber"></i> Vàng: góc mục tiêu</p><p class="target-safety">Không tự gửi lệnh hoặc giữ góc thật trên Raspberry Pi.</p>
      </div></div>
  </div>
  <div class="grid2 section-gap">
    <div class="card card-pad">${cardHead('Reaction wheel / Tốc độ bánh đà',`<span class="tag blue">ACT · 0x08E4</span>`)}<div class="chart-shell"><canvas id="chartWheel" aria-label="Tốc độ bánh đà và tốc độ đặt"></canvas></div><div class="chart-legend"><span><i class="legend-dot blue"></i> Measured/model (rad/s)</span><span><i class="legend-dot amber"></i> Setpoint (rad/s)</span></div></div>
    <div class="card card-pad">${cardHead('Light tracking / Cảm biến ánh sáng',`<span class="tag amber">LIGHT · 0x08DC</span>`)}<div class="chart-shell"><canvas id="chartLight" aria-label="Biểu đồ độ lệch ánh sáng"></canvas></div><div class="chart-legend"><span><i class="legend-dot amber"></i> Normalized diff (R−L)/(R+L)</span></div></div>
  </div>
  <details class="overview-more section-gap"><summary>Chi tiết thêm: ứng dụng và sự kiện <span class="muted">(mở khi cần)</span></summary>
    <div class="grid-alt section-gap">
      <div class="card card-pad">${cardHead('Trạng thái ứng dụng',`<button class="link-button" data-page="apps">Xem tất cả ↗</button>`)}<div id="overviewApps"></div></div>
      <div class="card card-pad">${cardHead('Sự kiện gần đây',`<button class="link-button" data-page="events">Nhật ký ↗</button>`)}<div id="overviewEvents" class="event-feed"></div></div>
    </div>
  </details>`;
}
function renderAppList(){
  return catalog.map(a=>{
    const stats=S?.apps?.[a.id]||{};
    return `<div class="app-row"><span class="app-logo" style="color:${color[a.id]}">${iconFor(a.id)}</span><div class="app-row-main"><strong>${esc(a.id.toUpperCase())}</strong><small>${esc(a.subtitle)}</small></div><div class="app-right">${statusChip(a.id)}<small>RX ${esc(stats.packets||0)} PKT</small></div></div>`;
  }).join('');
}
function renderEventFeed(){
  const e=(S?.events||[]).slice(0,5);
  if(!e.length)return '<div class="empty">Chưa có sự kiện</div>';
  return e.map(x=>`<div class="event-line"><span class="event-dash ${x.level.toLowerCase()}"></span><div><div class="event-message"><b>${esc(x.source)}</b> · ${esc(x.message)}</div><div class="event-time">${esc(niceTime(x.time))} UTC</div></div></div>`).join('');
}
function renderApps(){
  return heading('Ứng dụng cFS','Danh mục ứng dụng và message IDs được đối chiếu trực tiếp với các file cấu hình C trong repo.','02 · APPLICATION STATUS')+
  `<div class="app-cards">${catalog.map(a=>{
    const c=S?.apps?.[a.id]||{};
    return `<div class="card app-card"><div class="app-card-top"><span class="app-icon" style="color:${color[a.id]}">${iconFor(a.id)}</span><div style="flex:1"><h2>${esc(a.id.toUpperCase())}</h2><p>${esc(a.subtitle)}</p></div>${statusChip(a.id)}</div><p class="app-description">${esc(a.description)}</p><div class="app-data-line"><span>COMMAND MID</span><b>${a.cmd_mid}</b></div><div class="app-data-line"><span>HOUSEKEEPING</span><b>${a.hk_mid}</b></div><div class="app-data-line"><span>DATA STREAM</span><b>${a.data_mid||'CHƯA CÓ'}</b></div><div class="app-data-line"><span>FUNCTION CODES</span><b>${a.command_items.length} CMD</b></div><div class="app-data-line"><span>ĐÃ NHẬN / CMD</span><b>${c.packets||0} PKT · ${c.command_counter||0} CMD</b></div><div class="app-card-actions"><small class="muted mono">${esc(a.file)}</small><button class="btn btn-ghost btn-sm" data-app-action="${a.id}">Điều khiển ↗</button></div></div>`;
  }).join('')}</div>
  <div class="notice teal section-gap">Các ứng dụng <b>ADCS</b> và <b>CAMERA</b> chưa có gói telemetry data chuyên biệt trong source hiện tại. Web chỉ hiển thị housekeeping và lệnh có thật, không tạo thêm các chế độ điều khiển chưa được lập trình.</div>`;
}
function renderCommands(){
  const a=appBy(cmdApp)||catalog[0];if(!a)return '';
  const items=[...a.command_items,{name:'REQUEST_HK',cc:null,description:'Yêu cầu housekeeping',payload:'MID SEND_HK riêng'}];
  if(!items.some(c=>c.name===cmdName))cmdName='NOOP';
  const c=items.find(c=>c.name===cmdName)||items[0];
  const param=cmdName==='SET_WHEEL_SPEED'?`<div class="field"><label for="fieldWheel">OMEGA_RAD_S · float · rad/s</label><input id="fieldWheel" type="number" min="-10000" max="10000" value="120" step="1" inputmode="decimal"></div>`:
    cmdName==='DISPLAY_PARAM'?`<div class="form-grid"><div class="field"><label for="fieldU32">VAL_U32</label><input id="fieldU32" type="number" min="0" max="4294967295" value="42"></div><div class="field"><label for="fieldI16">VAL_I16</label><input id="fieldI16" type="number" min="-32768" max="32767" value="-7"></div><div class="field"><label for="fieldStr">VAL_STR · MAX 9 BYTES</label><input id="fieldStr" maxlength="9" value="ADCS"></div></div>`:
    `<div class="notice teal">Lệnh này không có tham số payload. ${cmdName==='RECALIBRATE'?'Giữ yên cảm biến IMU để hiệu chuẩn.':cmdName==='RESET_ANGLE'?'Góc tích phân IMU sẽ được đặt về 0.':cmdName==='STOP_WHEEL'?'Bánh đà sẽ giảm tốc về 0, sau đó phanh.':'Trạm mặt đất sẽ gửi lệnh tới ứng dụng được chọn.'}</div>`;
  const last=S?.last_result;
  return heading('Command Control','Gửi lệnh theo Function Code và theo dõi phản hồi mô phỏng hoặc kết quả uplink.','03 · COMMAND UPLINK',`<span class="tag ${S?.mode==='live'?'amber':''}">${S?.mode==='simulation'?'SIM ACK / NO HARDWARE':S?.mode==='live'?'LIVE · OPERATOR CONFIRM':'REPLAY · READ ONLY'}</span>`)+`
  <div class="command-layout">
    <div class="card cmd-app-select"><div class="section-label" style="margin:4px 11px 17px">SELECT APPLICATION</div>${catalog.map(x=>`<button class="cmd-app-button ${cmdApp===x.id?'active':''}" data-cmd-app="${x.id}"><span class="app-logo" style="color:${color[x.id]}">${iconFor(x.id)}</span>${esc(x.id.toUpperCase())}<small>${x.cmd_mid}</small></button>`).join('')}<div class="notice" style="margin-top:21px">Gói lệnh thực tế được gửi bằng <b>cFS cmdUtil</b> khi LIVE được cấu hình và xác nhận riêng. Ở SIM tất cả phản hồi chỉ là giả lập.</div></div>
    <div class="stack">
      <div class="card command-panel">${cardHead(`${a.id.toUpperCase()} / Các tác vụ`, `<span class="tag blue">CMD MID ${a.cmd_mid}</span>`)}<div class="command-list">${items.map(item=>`<button data-cmd="${item.name}" class="cmd-pick ${cmdName===item.name?'active':''}"><span class="cc-number">${item.cc===null?'HK':`CC ${item.cc}`}</span><strong>${esc(item.name)}</strong><small>${esc(item.description)}</small></button>`).join('')}</div>
        <div class="cmd-form"><div class="cmd-form-head"><h3>${esc(cmdName)}</h3><span class="tag ${cmdName==='STOP_WHEEL'?'amber':'dim'}">${c.cc===null?`HK MID ${a.hk_mid}`:`CC ${c.cc}`}</span></div><p>${esc(c.description)} · ${esc(c.payload)}</p>${param}<div class="cmd-form-foot"><span class="warn-text">${S?.mode==='live'?'⚠ Gửi thiết bị thật · yêu cầu xác nhận':'◉ Demo mode · không phát lệnh qua mạng'}</span><button class="btn btn-primary" data-action="send-command" ${S?.mode==='replay'?'disabled':''}>${S?.mode==='simulation'?'▶ Chạy mô phỏng':'↑ Gửi lệnh'} <span>↗</span></button></div></div>
      </div>
      <div class="card card-pad">${cardHead('Kết quả lệnh gần nhất',`<span class="tag dim">${last?niceTime(last.time)+' UTC':'NO COMMAND'}</span>`)}<div id="cmdLastResult">${renderLastResult()}</div></div>
    </div>
  </div>`;
}
function renderLastResult(){
  const last=S?.last_result;
  if(!last)return '<div class="empty"><span class="empty-icon">⌘</span><strong>Chưa gửi tác vụ nào</strong>Chọn ứng dụng và lệnh để chạy mô phỏng.</div>';
  return `<div class="last-result ${last.status==='SIM_ACK'||last.status==='SENT_UNCONFIRMED'?'':'error'}"><strong>${esc(last.status)} · ${esc(last.app.toUpperCase())} / ${esc(last.name)}</strong><p>${esc(last.message)}</p><p class="mono">${esc(last.cmd_mid)} · ${last.cc===null?'HK':`CC ${esc(last.cc)}`} · ${esc(niceTime(last.time))} UTC</p></div>`;
}
const fieldUnits={raw_rate_rad_s:'rad/s',rate_rad_s:'rad/s',angle_rad:'rad',bias_rad_s:'rad/s',temp_c:'°C',dt_s:'s',sample_counter:'count',valid:'bool',status:'code',stationary:'bool',simulated:'bool',left_lux:'lux',right_lux:'lux',normalized_diff:'',bearing_rad:'rad',error_valid:'bool',cmd_omega_rad_s:'rad/s',target_omega_rad_s:'rad/s',meas_omega_rad_s:'rad/s',pfm_hz:'Hz',saturated:'bool',enabled:'bool',braking:'bool',direction:'±1',measured:'bool',CommandCounter:'count',CommandErrorCounter:'count'};
function getFields(id){
  if(id==='adcs_app'||id==='camera_app')return {CommandCounter:S?.apps[id]?.command_counter??null,CommandErrorCounter:S?.apps[id]?.command_error_counter??null};
  return S?.telemetry?.[id]||{};
}
function renderFieldTable(){
 const fields=getFields(tlmApp);const rows=Object.entries(fields);
 if(!rows.length)return '<div class="empty">Chưa có dữ liệu. Bật mô phỏng hoặc gửi telemetry vào API.</div>';
 return `<table class="data-table"><thead><tr><th>FIELD</th><th>VALUE</th></tr></thead><tbody>${rows.map(([key,value])=>`<tr><td class="mono">${esc(key)} <span class="muted">${esc(fieldUnits[key]||'')}</span></td><td>${typeof value==='number'?esc(Number.isInteger(value)?value:F(value,4)):esc(value)}</td></tr>`).join('')}</tbody></table>`;
}
function renderTelemetry(){
 const a=appBy(tlmApp)||catalog[0];const activePackets=S?.apps[tlmApp]?.packets||0;
 return heading('Telemetry Explorer','Theo dõi giá trị SI nguyên bản trong packet của IMU, LIGHT và ACT; hỗ trợ nhập replay JSON.','04 · TELEMETRY DOWNLINK', exportLinks())+
 `<div class="card card-pad">${cardHead('Dòng dữ liệu / Stream selection',`<span class="tag">${simTag()}</span>`)}<div class="tlm-select">${catalog.map(x=>`<button class="${tlmApp===x.id?'active':''}" data-tlm-app="${x.id}">${x.id.toUpperCase()}</button>`).join('')}</div><div class="grid2 section-gap"><div class="card card-pad" style="background:#122035"><div class="section-label">CMD MID</div><div class="stat-value stat-blue" style="font-size:25px">${a.cmd_mid}</div><div class="tiny-note">${esc(a.subtitle)}</div></div><div class="card card-pad" style="background:#122035"><div class="section-label">TELEMETRY MID</div><div class="stat-value stat-accent" style="font-size:25px">${a.data_mid||a.hk_mid}</div><div class="tiny-note">${esc(activePackets)} packet(s) received</div></div></div></div>
 <div class="tlm-layout section-gap"><div class="stack"><div class="card card-pad">${cardHead('Dữ liệu lịch sử',`<span class="tag dim">LAST 180 SAMPLES</span>`)}<div class="chart-shell tall"><canvas id="chartTlm"></canvas></div><div class="chart-legend" id="tlmLegend"></div></div><div class="card card-pad">${cardHead('Gói gần nhất','<span class="tag blue">PAYLOAD FIELDS</span>')}<div class="field-table" id="fieldTable">${renderFieldTable()}</div></div></div><div class="stack"><div class="card card-pad">${cardHead('Thông tin kết nối')}<div class="app-data-line"><span>ỨNG DỤNG</span><b>${esc(a.id.toUpperCase())}</b></div><div class="app-data-line"><span>TRẠNG THÁI</span>${statusChip(a.id)}</div><div class="app-data-line"><span>PACKET / SESSION</span><b>${activePackets}</b></div><div class="app-data-line"><span>FILE NGUỒN</span><b style="font-size:9px;text-align:right;overflow-wrap:anywhere">${esc(a.file)}</b></div><div class="app-data-line"><span>LAST SEEN</span><b id="tlmLastSeen">${S?.apps[a.id]?.last_seen?niceTime(S.apps[a.id].last_seen)+' UTC':'—'}</b></div></div><div class="card card-pad">${cardHead('Nhập dữ liệu trước khi kết nối')}<p class="help-copy">Tải file JSON chứa danh sách gói theo định dạng <code>[{"app":"imu_app","payload":{...}}]</code>. Replay không gửi lệnh thật.</p><label class="field"><span class="section-label">REPLAY FILE .JSON</span><input type="file" id="replayFile" accept=".json,application/json"></label><button class="btn btn-primary btn-block" style="margin-top:13px" data-action="load-replay">↑ Nhập & Replay</button></div></div></div>`;
}
function renderEvents(){
 const events=(S?.events||[]).filter(e=>eventFilter==='ALL'||e.level===eventFilter);
 return heading('Event & Command Log','Theo dõi lệnh đã gửi, phản hồi giả lập, cảnh báo và lịch sử điều khiển.','05 · EVENT LOGGING',`<button class="btn btn-ghost" data-action="export-events">↓ Xuất log JSON</button>`)+
 `<div class="event-toolbar"><div class="filter-pills">${['ALL','COMMAND','INFO','WARN','ERROR'].map(f=>`<button class="${eventFilter===f?'active':''}" data-filter="${f}">${f}</button>`).join('')}</div><span class="mono muted" style="font-size:11px">${events.length} EVENTS</span></div><div class="card event-card"><div class="table-wrap"><table class="data-table"><thead><tr><th>UTC</th><th>LEVEL</th><th>APP / SOURCE</th><th>MESSAGE</th></tr></thead><tbody>${events.map(e=>`<tr><td class="mono">${esc(niceTime(e.time))}</td><td><span class="tag ${e.level==='ERROR'?'red':e.level==='WARN'?'amber':e.level==='COMMAND'?'blue':'dim'}">${esc(e.level)}</span></td><td class="mono">${esc(e.source)}</td><td>${esc(e.message)}</td></tr>`).join('')||'<tr><td colspan="4" class="muted">Không có sự kiện tương ứng.</td></tr>'}</tbody></table></div></div>`;
}
function renderConnectionPanel(){
 const conn=S?.connection||{},c=conn.config||{};
 const running=!!conn.running, live=S?.mode==='live';
 const field=(id,label,value,extra='')=>`<div class="field"><label for="${id}">${label}</label><input id="${id}" type="text" value="${esc(value||'')}" ${running?'disabled':''} ${extra}></div>`;
 const portField=(id,label,value)=>`<div class="field"><label for="${id}">${label}</label><input id="${id}" type="number" min="1" max="65535" step="1" value="${esc(value??'')}" ${running?'disabled':''}></div>`;
 return `<div class="card card-pad" id="cfsConnectionCard">
   ${cardHead('Kết nối Raspberry Pi 3',`<span class="tag ${conn.status==='RECEIVING'?'green':running?'blue':'amber'}" id="linkStatus">${esc(conn.status||'STOPPED')}</span>`)}
   <div class="quick-guide"><strong>3 bước để nhận dữ liệu thật</strong><p><b>1.</b> Chọn <b>LIVE</b> → <b>2.</b> Nhập IP Pi và Ubuntu → <b>3.</b> Bấm <b>Kết nối</b></p></div>
   <div class="field"><label for="linkSource">Nhận telemetry qua</label><select id="linkSource" ${running?'disabled':''}><option value="nasa_zmq" ${c.source==='nasa_zmq'?'selected':''}>NASA GroundSystem (ZeroMQ)</option><option value="direct_udp" ${c.source==='direct_udp'?'selected':''}>UDP trực tiếp</option></select></div>
   <div class="grid2 compact-fields">${field('linkTargetIp','IP Raspberry Pi',c.target_ip)}${field('linkGroundIp','IP Ubuntu nhận telemetry',c.ground_ip)}</div>
   <details class="advanced-settings" id="advancedConnection"><summary>Cấu hình nâng cao <span>Port, alias, IPC, cmdUtil</span></summary>
     <div class="grid2 compact-fields">${portField('linkCommandPort','Cổng lệnh UDP',c.command_port)}${portField('linkTelemetryPort','Cổng telemetry UDP',c.telemetry_port)}</div>
     <div class="grid2 compact-fields">${field('linkAlias','Spacecraft alias',c.spacecraft_alias)}${field('linkBindIp','UDP listen IP',c.bind_ip)}</div>
     ${field('linkIpc','NASA IPC Routing',c.nasa_ipc)}
     ${field('linkCmdUtil','Đường dẫn NASA cmdUtil',c.cmdutil_path)}
   </details>
   <p id="linkSourceTip" class="connection-hint">${c.source==='nasa_zmq'?'NASA GroundSystem phải đang mở cùng user Linux. Web đọc qua ZeroMQ, không giữ cổng 2234.':'UDP trực tiếp: đóng NASA GroundSystem trước để không tranh cổng telemetry.'}</p>
   <div class="link-action-row main-connection-actions"><button class="btn btn-ghost" data-action="link-save" ${running?'disabled':''}>Lưu</button><button class="btn btn-primary" data-action="link-start" ${!live||running?'disabled':''}>Kết nối</button><button class="btn btn-ghost" data-action="link-stop" ${!running?'disabled':''}>Ngắt</button></div>
   <div class="connection-stats"><div><small>Trạng thái</small><strong id="linkStateText">${esc(conn.status||'STOPPED')}</strong></div><div><small>Gói nhận</small><strong id="linkRaw">${conn.received_datagrams||0}</strong></div><div><small>Đã giải mã</small><strong id="linkDecoded">${conn.decoded_packets||0}</strong></div></div>
   <div id="linkError" class="notice ${conn.last_error?'amber':'teal'}" style="${conn.last_error?'':'display:none'}">${esc(conn.last_error||'')}</div>
   <details class="advanced-settings diagnostic-settings"><summary>Thông tin nhận dữ liệu <span>Packet gần nhất / sender / NASA topic</span></summary>
     <div class="app-data-line"><span>LAST PACKET</span><b id="linkLast">${esc(conn.last_packet_time||'—')}</b></div>
     <div class="app-data-line"><span>SENDER / ALIAS</span><b id="linkSender">${esc(conn.last_sender||'—')}</b></div>
     <div class="app-data-line"><span>NASA TOPIC</span><b id="linkTopic" class="connection-break">${esc(conn.last_topic||'—')}</b></div>
   </details>
   <div class="divider-line"></div>
   ${cardHead('Lệnh LIVE qua NASA',`<span class="tag ${conn.uplink_enabled&&conn.cmdutil_ready?'green':'amber'}" id="linkCmdStatus">${conn.uplink_enabled&&conn.cmdutil_ready?'AVAILABLE':'LOCKED'}</span>`)}
   <p class="connection-hint">Chỉ gửi lệnh khi backend cho phép và đã kiểm tra phần cứng. Bật telemetry không phải bằng chứng thiết bị đã chấp nhận lệnh.</p>
   <div class="link-action-row"><button class="btn btn-primary" data-action="link-enable-tlm" ${!running||!live||!conn.cmdutil_ready||!conn.uplink_enabled?'disabled':''}>Bật telemetry từ Pi</button></div>
   <details class="advanced-settings operator-safety" ${conn.armed?'open':''}><summary>Điều khiển LIVE nâng cao <span id="linkArmText">${conn.armed?'ARMED · '+conn.arm_seconds_left+'s':'DISARMED'}</span></summary>
     <div class="link-action-row"><button class="btn btn-ghost" data-action="link-arm" ${!running||!live||!conn.cmdutil_ready||!conn.uplink_enabled?'disabled':''}>ARM 60 giây</button><button class="btn btn-danger" data-action="link-disarm" ${!conn.armed?'disabled':''}>DISARM</button></div>
     <div class="notice">LIVE chỉ hoạt động khi <code>ADCS_UPLINK_ENABLED=1</code>, cmdUtil đã build và người vận hành xác nhận lệnh. Giữ nguyên ARM 60 giây và telemetry stale checks trong backend. <code>SENT_UNCONFIRMED</code> chưa phải ACK.</div>
   </details>
  </div>`;
}
function updateConnectionPanel(){
 const c=S?.connection||{};
 const setText=(id,content)=>{const node=$('#'+id);if(node)node.textContent=String(content??'—')};
 setText('linkStatus',c.status||'STOPPED');setText('linkStateText',c.status||'STOPPED');
 setText('linkRaw',c.received_datagrams??0);setText('linkDecoded',c.decoded_packets??0);
 setText('linkLast',c.last_packet_time||'—');setText('linkSender',c.last_sender||'—');
 setText('linkTopic',c.last_topic||'—');
 setText('linkArmText',c.armed?`ARMED · ${c.arm_seconds_left}s`:'DISARMED');
 setText('linkCmdStatus',c.cmdutil_ready&&c.uplink_enabled?'AVAILABLE':'LOCKED');
 const error=$('#linkError');if(error){error.textContent=c.last_error||'';error.style.display=c.last_error?'':'none'}
}
function getConnectionForm(){
 return {source:$('#linkSource').value,target_ip:$('#linkTargetIp').value.trim(),
 command_port:Number($('#linkCommandPort').value),telemetry_port:Number($('#linkTelemetryPort').value),
 ground_ip:$('#linkGroundIp').value.trim(),spacecraft_alias:$('#linkAlias').value.trim(),
 bind_ip:$('#linkBindIp').value.trim(),nasa_ipc:$('#linkIpc').value.trim(),
 cmdutil_path:$('#linkCmdUtil').value.trim()};
}
async function linkAction(action){
 try{
  let resp;
  if(action==='link-save'||action==='link-start'){
   if(!S?.connection?.running){
    resp=await api('/api/connection/config','POST',getConnectionForm());
    S.connection=resp;
   }
   if(action==='link-save'){toast('Đã lưu IP, cổng và cấu hình NASA trên Ubuntu');navigate('settings');return}
  }
  if(action==='link-start')resp=await api('/api/connection/start','POST',{});
  if(action==='link-stop')resp=await api('/api/connection/stop','POST',{});
  if(action==='link-arm'){
   if(!window.confirm('ARM uplink trong 60 giây? Chỉ thao tác khi phần cứng an toàn.'))return;
   resp=await api('/api/connection/arm','POST',{enabled:true});
  }
  if(action==='link-disarm')resp=await api('/api/connection/arm','POST',{enabled:false});
  if(action==='link-enable-tlm'){
   if(!window.confirm(`Gửi lệnh TO_LAB yêu cầu Raspberry Pi phát telemetry về ${S.connection.config.ground_ip}:2234? Chưa có xác nhận từ cFS.`))return;
   resp=await api('/api/connection/enable-tlm','POST',{confirm_live:true});
   toast(resp.status+': '+resp.message);
  }
  S=await api('/api/state');navigate('settings');
  if(action!=='link-enable-tlm')toast(action==='link-start'?'Đã khởi động bộ nhận. Chờ telemetry để xác nhận kết nối.':action==='link-stop'?'Đã ngắt bộ nhận':action==='link-arm'?'ARM trong 60 giây':'Đã cập nhật kết nối');
 }catch(err){toast(err.message,true)}
}
function renderSettings(){
 return heading('Cấu hình & Kết nối','Chọn chế độ hoạt động và kết nối Raspberry Pi khi cần.','06 · SYSTEM CONFIGURATION')+
 `<div class="settings-layout"><div class="stack"><div class="card card-pad">${cardHead('Chế độ vận hành',`<span class="tag">${(S?.mode||'SIM').toUpperCase()}</span>`)}
  <label class="option-item ${S?.mode==='simulation'?'selected':''}" data-mode="simulation"><div><strong>Simulation · Thử giao diện</strong><small>Dữ liệu giả lập, không gửi lệnh tới Pi.</small></div><input type="radio" name="mode" value="simulation" ${S?.mode==='simulation'?'checked':''}></label>
  <label class="option-item ${S?.mode==='live'?'selected':''}" data-mode="live"><div><strong>LIVE · Raspberry Pi</strong><small>Nhận dữ liệu thật. Lệnh phần cứng vẫn bị khóa mặc định.</small></div><input type="radio" name="mode" value="live" ${S?.mode==='live'?'checked':''}></label>
  <label class="option-item ${S?.mode==='replay'?'selected':''}" data-mode="replay"><div><strong>Replay · Xem dữ liệu đã lưu</strong><small>Không gửi lệnh thật.</small></div><input type="radio" name="mode" value="replay" ${S?.mode==='replay'?'checked':''}></label>
  <div class="notice teal">Mode hiện tại: <b>${simTag()}</b> · ${S?.mode==='live'?'Trạng thái gửi lệnh thật: '+(S?.uplink_configured?'ĐÃ BẬT':'ĐANG KHÓA'):S?.mode==='simulation'?'Dữ liệu được tạo bởi backend Python':'Dữ liệu từ file hoặc API'}</div></div>
 <details class="card card-pad expandable-card"><summary>Tuỳ chỉnh mô phỏng <span class="muted">(mở khi cần)</span></summary><div class="expandable-content">${cardHead('Bộ tạo dữ liệu mô phỏng')}<p class="help-copy">Các tình huống thử nghiệm được xây dựng dựa trên trạng thái cảm biến có trong source.</p><div class="sim-controls"><div class="field"><label for="scenarioSelect">SCENARIO</label><select id="scenarioSelect" ${S?.mode!=='simulation'?'disabled':''}><option value="normal">Normal / Danh định</option><option value="stationary">Stationary / IMU đứng yên</option><option value="dark">Light: DARK</option><option value="light_error">Light: IO ERROR</option><option value="light_saturated">Light: SATURATED</option></select></div><button class="btn btn-primary" data-action="sim-toggle" ${S?.mode!=='simulation'?'disabled':''}>${S?.running?'Ⅱ Tạm dừng':'▶ Tiếp tục'}</button></div><p class="tiny-note">Trạng thái SIMULATED=1 luôn được đánh dấu trong các payload mô phỏng.</p></div></details>
 </div><div class="stack"> ${renderConnectionPanel()}
<details class="card card-pad expandable-card"><summary>Bridge / Telemetry API <span class="muted">(kỹ thuật)</span></summary><div class="expandable-content">${cardHead('Bridge / Telemetry API')}<p class="help-copy">Đẩy dữ liệu từ một bridge cFS vào web khi đã bật LIVE. Dùng token <code>X-ADCS-Token</code> nếu máy chủ đã cấu hình.</p><pre class="api-example">curl -X POST http://127.0.0.1:8000/api/ingest \\
  -H 'Content-Type: application/json' \\
  -d '{"app":"imu_app","payload":{"rate_rad_s":0.02,"angle_rad":1.2,"valid":1,"simulated":0}}'</pre><p class="help-copy">Xem <code>README.md</code> để bật bộ nhận CCSDS UDP và cách cấu hình uplink cmdUtil.</p></div></details>
 <details class="card card-pad expandable-card"><summary>Chi tiết nguồn dữ liệu <span class="muted">(kỹ thuật)</span></summary><div class="expandable-content">${cardHead('Nguồn gốc dữ liệu')}<p class="help-copy">Đối chiếu trực tiếp từ ZIP: <code>apps/imu_app</code>, <code>apps/light_app</code>, <code>apps/act_app</code>, <code>apps/adcs_app</code>, <code>apps/camera_app</code> và <code>docs/*/*_VI.md</code>.</p><div class="notice">Đây là hệ thống phục vụ phát triển / kiểm thử. Chưa được kiểm định để điều khiển phần cứng trên nhiệm vụ bay thật.</div></div></details></div></div>`;
}
function navigate(next){
 if(!names[next])return;
 page=next;$$('.nav-btn').forEach(b=>b.classList.toggle('active',b.dataset.page===next));$('#crumb').textContent=names[next];
 $('#view').innerHTML=({overview:renderOverview,apps:renderApps,commands:renderCommands,telemetry:renderTelemetry,events:renderEvents,settings:renderSettings})[page]();
 $('.sidebar').classList.remove('open');
 if(page==='settings'&&$('#scenarioSelect'))$('#scenarioSelect').value=S?.scenario||'normal';
 updateLive();
}
function updateLive(){
 if(!S)return;
 const m=S.mode;
 $('#modeChip').className='mode-chip '+(m==='live'?'live':m==='replay'?'replay':'');
 $('#modeChip').innerHTML=`<i></i> ${m.toUpperCase()}${m==='simulation'&&!S.running?' · PAUSED':''}`;
 $('#sideMode').textContent=(m==='simulation'?'SIMULATION':m==='live'?'LIVE TELEMETRY':'REPLAY')+' '+(m==='simulation'&&S.running?'ONLINE':m==='live'?'MODE':'READY');
 $('#sideState').textContent=m==='simulation'?(S.running?'Đang tạo dữ liệu giả lập':'Tạm dừng mô phỏng'):m==='live'?'Chờ dữ liệu từ cFS/bridge':'Dữ liệu nhập từ file JSON';
 if(page==='settings')updateConnectionPanel();
 if(page==='overview'){
   const i=S.telemetry.imu_app||{},a=S.telemetry.act_app||{},l=S.telemetry.light_app||{};
   const bind=(name,value)=>{let x=$(`[data-bind="${name}"]`);if(x)x.textContent=value;};
   bind('imuRate',i.rate_rad_s===undefined?'—':F(i.rate_rad_s*DEG,2));
   bind('imuAngle',i.angle_rad===undefined?'—':F(i.angle_rad*DEG,1));
   bind('wheel',a.meas_omega_rad_s===undefined?'—':F(a.meas_omega_rad_s,1));
   bind('packets',S.packets.toLocaleString('en-US'));
   const needle=$('#axisNeedle');if(needle)needle.style.transform=`rotate(${(i.angle_rad||0)*DEG%360}deg)`;
   if($('#measureAngle'))$('#measureAngle').textContent=i.angle_rad===undefined?'—':F(i.angle_rad*DEG,1);
   if($('#measureBias'))$('#measureBias').textContent=i.bias_rad_s===undefined?'—':F(i.bias_rad_s*DEG,3);
   if($('#measureValid'))$('#measureValid').textContent=i.valid===undefined?'—':i.valid?'YES':'NO';
   updateTargetReference();
   if($('#overviewApps'))$('#overviewApps').innerHTML=renderAppList();
   if($('#overviewEvents'))$('#overviewEvents').innerHTML=renderEventFeed();
   if($('#rateDataTag'))$('#rateDataTag').textContent=simTag();
   drawChart('chartRate',[{key:'rate_rad_s',scale:DEG,color:'#52dbc4'}]);
   drawChart('chartWheel',[{key:'wheel_rad_s',scale:1,color:'#83bafa'},{key:'wheel_set',scale:1,color:'#f3c98b'}]);
   drawChart('chartLight',[{key:'light_error',scale:1,color:'#f3c98b'}]);
 }
 if(page==='telemetry'){
   if($('#fieldTable'))$('#fieldTable').innerHTML=renderFieldTable();
   const app=S.apps[tlmApp];if($('#tlmLastSeen'))$('#tlmLastSeen').textContent=app?.last_seen?niceTime(app.last_seen)+' UTC':'—';
   const schema={imu_app:[{key:'rate_rad_s',scale:DEG,color:'#52dbc4',label:'Rate · °/s'},{key:'angle_rad',scale:DEG,color:'#c5a2fa',label:'Angle · deg'}],act_app:[{key:'wheel_rad_s',scale:1,color:'#83bafa',label:'Speed · rad/s'},{key:'wheel_set',scale:1,color:'#f3c98b',label:'Setpoint · rad/s'}],light_app:[{key:'light_error',scale:1,color:'#f3c98b',label:'Normalized diff'}]};
   const series=schema[tlmApp]||[];drawChart('chartTlm',series);
   if($('#tlmLegend'))$('#tlmLegend').innerHTML=series.map(s=>`<span><i class="legend-dot" style="background:${s.color}"></i>${s.label}</span>`).join('')||'<span>Housekeeping · không có dữ liệu chuỗi liên tục</span>';
 }
 if(page==='commands'&&$('#cmdLastResult'))$('#cmdLastResult').innerHTML=renderLastResult();
 if(page==='events'){
   // The events table is updated in place only after a new event count arrives.
   const sig=(S.events||[]).map(e=>e.id).join(',');
   if(window._eventSig!==sig){window._eventSig=sig;$('#view').innerHTML=renderEvents();}
 }
}
function drawChart(id,series){
 const canvas=$('#'+id);if(!canvas)return;
 const ctx=canvas.getContext('2d');const rect=canvas.getBoundingClientRect();
 const w=rect.width||400,h=rect.height||200,dpr=Math.max(1,Math.min(2,window.devicePixelRatio||1));
 if(canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)){canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr)}
 ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);
 const left=44,right=14,top=11,bottom=25,plotW=Math.max(20,w-left-right),plotH=Math.max(20,h-top-bottom);
 const entries=(S?.history||[]).slice(-110);
 ctx.strokeStyle='rgba(120,152,175,.15)';ctx.fillStyle='#758ba0';ctx.font='10px Consolas,monospace';ctx.textAlign='right';ctx.lineWidth=1;
 const values=entries.flatMap(e=>series.map(s=>typeof e[s.key]==='number'?e[s.key]*s.scale:null)).filter(v=>v!==null&&Number.isFinite(v));
 let lo=values.length?Math.min(...values):-.1,hi=values.length?Math.max(...values):.1;
 const pad=Math.max((hi-lo)*.18,.08);lo-=pad;hi+=pad;
 for(let j=0;j<5;j++){
  const y=top+plotH*j/4;ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(w-right,y);ctx.stroke();
  const v=hi-(hi-lo)*j/4;ctx.fillText((Math.abs(v)>=100?Math.round(v):v.toFixed(Math.abs(v)>=10?1:2)),left-9,y+3);
 }
 ctx.textAlign='left';ctx.fillStyle='#5b7085';ctx.fillText('−'+Math.round(entries.length/5)+'s',left,h-7);
 ctx.textAlign='right';ctx.fillText('NOW',w-right,h-7);
 if(!values.length){ctx.textAlign='center';ctx.fillStyle='#6e8397';ctx.font='12px sans-serif';ctx.fillText('Chưa có dữ liệu telemetry',w/2,h/2);return}
 for(const ser of series){
  const points=entries.map((e,j)=>({x:left+plotW*j/Math.max(1,entries.length-1),value:typeof e[ser.key]==='number'?e[ser.key]*ser.scale:null}));
  ctx.strokeStyle=ser.color;ctx.lineWidth=2;ctx.lineJoin='round';ctx.lineCap='round';ctx.beginPath();let drawing=false;
  for(const p of points){if(p.value===null||!Number.isFinite(p.value)){drawing=false;continue}const y=top+(hi-p.value)/(hi-lo)*plotH;if(!drawing){ctx.moveTo(p.x,y);drawing=true}else ctx.lineTo(p.x,y)}ctx.stroke();
  const last=[...points].reverse().find(p=>p.value!==null&&Number.isFinite(p.value));if(last){const y=top+(hi-last.value)/(hi-lo)*plotH;ctx.beginPath();ctx.arc(last.x,y,3.2,0,Math.PI*2);ctx.fillStyle=ser.color;ctx.fill()}
 }
}
function download(name,text,mime){const blob=new Blob([text],{type:mime});const href=URL.createObjectURL(blob),a=document.createElement('a');a.href=href;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(href),1000)}
async function doCommand(confirmed=false){
 const params={};
 if(cmdName==='SET_WHEEL_SPEED')params.omega_rad_s=Number($('#fieldWheel').value);
 if(cmdName==='DISPLAY_PARAM'){params.ValU32=Number($('#fieldU32').value);params.ValI16=Number($('#fieldI16').value);params.ValStr=$('#fieldStr').value;}
 if(S?.mode==='live'&&!confirmed){
  const modal=$('#modalHost');modal.innerHTML=`<div class="modal-backdrop" role="presentation"><div class="modal" role="dialog" aria-modal="true"><div class="eyebrow">LIVE UPLINK · SAFETY</div><h2>Xác nhận gửi lệnh tới cFS</h2><p>Bạn đang gửi <b>${esc(cmdName)}</b> tới <b>${esc(cmdApp)}</b> (${appBy(cmdApp)?.cmd_mid}) trên hệ thống thật. Dữ liệu và phản hồi sẽ không được mô phỏng. Chỉ tiếp tục nếu bạn đã xác nhận phần cứng an toàn.</p><div class="notice">Lệnh điều khiển bánh đà có thể gây chuyển động cơ khí. Trạm mặt đất không thay thế interlock phần cứng.</div><div class="modal-actions"><button class="btn btn-ghost" id="closeModal">Hủy</button><button class="btn btn-danger" id="confirmLive">Xác nhận uplink</button></div></div></div>`;
  $('#closeModal').onclick=()=>modal.innerHTML='';$('#confirmLive').onclick=()=>{modal.innerHTML='';doCommand(true)};return;
 }
 try{
  const result=await api('/api/command','POST',{app:cmdApp,name:cmdName,params,confirm_live:confirmed});
  toast(`${result.status}: ${cmdApp} / ${cmdName}`);S=await api('/api/state');updateLive();
 }catch(e){toast(e.message,true)}
}
async function changeMode(mode){
 try{await api('/api/mode','POST',{mode});S=await api('/api/state');navigate('settings');toast('Chuyển chế độ '+mode.toUpperCase());}
 catch(e){toast(e.message,true)}
}
function addHandlers(){
 document.addEventListener('click',async e=>{
  const button=e.target.closest('button,[data-mode]');if(!button)return;
  if(button.matches('[data-page]'))return navigate(button.dataset.page);
  if(button.matches('[data-app-action]')){cmdApp=button.dataset.appAction;cmdName='NOOP';return navigate('commands')}
  if(button.matches('[data-cmd-app]')){cmdApp=button.dataset.cmdApp;cmdName='NOOP';return navigate('commands')}
  if(button.matches('[data-cmd]')){cmdName=button.dataset.cmd;return navigate('commands')}
  if(button.matches('[data-tlm-app]')){tlmApp=button.dataset.tlmApp;return navigate('telemetry')}
  if(button.matches('[data-filter]')){eventFilter=button.dataset.filter;return navigate('events')}
  if(button.matches('[data-mode]'))return changeMode(button.dataset.mode);
   if(button.dataset.action==='target-zero'){setTarget(0);return;}
  if(button.dataset.action==='send-command')return doCommand();
  if(button.dataset.action?.startsWith('link-'))return linkAction(button.dataset.action);
  if(button.dataset.action==='sim-toggle'){
    try{await api('/api/sim','POST',{running:!S.running});S=await api('/api/state');navigate('settings')}catch(err){toast(err.message,true)}return;
  }
  if(button.dataset.action==='export-json')return download('adcs_telemetry.json',JSON.stringify({mode:S.mode,telemetry:S.telemetry,history:S.history},null,2),'application/json');
  if(button.dataset.action==='export-events')return download('adcs_events.json',JSON.stringify(S.events,null,2),'application/json');
  if(button.dataset.action==='load-replay'){
    const file=$('#replayFile')?.files[0];if(!file)return toast('Hãy chọn file JSON trước.',true);
    try{const parsed=JSON.parse(await file.text());const packets=Array.isArray(parsed)?parsed:parsed.packets;
      if(!Array.isArray(packets))throw Error('File phải là mảng packets hoặc {"packets":[]}');
      const ret=await api('/api/replay','POST',{packets});S=await api('/api/state');navigate('telemetry');toast('Đã nhập '+ret.imported+' gói.');}
    catch(err){toast('Lỗi replay: '+err.message,true)}return;
  }
 });
 $('#menuBtn').addEventListener('click',()=>$('.sidebar').classList.toggle('open'));
 $('#quickExport').addEventListener('click',()=>window.location.assign('/api/export.csv'));
 document.addEventListener('input',e=>{if(e.target?.id==='targetZInput'||e.target?.id==='targetZSlider'){const value=Number(e.target.value);if(Number.isFinite(value))setTarget(value);}});
 document.addEventListener('change',async e=>{
  if(e.target?.id==='linkSource'){const tip=$('#linkSourceTip');if(tip)tip.textContent=e.target.value==='nasa_zmq'?'NASA GroundSystem phải đang mở cùng user Linux. Web đọc qua ZeroMQ, không giữ cổng 2234.':'UDP trực tiếp: đóng NASA GroundSystem trước để không tranh cổng telemetry.';}
  if(e.target?.id==='scenarioSelect')try{await api('/api/sim','POST',{scenario:e.target.value});S=await api('/api/state');toast('Đã đổi kịch bản mô phỏng')}catch(err){toast(err.message,true)}
 });
 window.addEventListener('resize',()=>updateLive());
}
async function refresh(){try{S=await api('/api/state');updateLive();}catch(err){if(!window._errorShown){toast('Mất kết nối tới server.py: '+err.message,true);window._errorShown=true}}}
async function boot(){
 utcTick();setInterval(utcTick,1000);addHandlers();
 try{const [cat,state]=await Promise.all([api('/api/catalog'),api('/api/state')]);catalog=cat.apps;S=state;navigate('overview');setInterval(refresh,1100)}
 catch(err){$('#view').innerHTML=`<div class="empty"><span class="empty-icon">⚠</span><strong>Không thể kết nối backend</strong>Chạy <code>python server.py</code> rồi mở <code>http://127.0.0.1:8000</code>. <p>${esc(err.message)}</p></div>`}
}
boot();
