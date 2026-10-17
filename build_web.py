"""Build a static, playable Vercel deployment from the verified public release."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from download_game import digest, extract_payload, target_path

HERE = Path(__file__).resolve().parent
PREFIX = 'mirror/playgta5.com/'


def patch_worker(code):
    old = 'if (wanted.size) await batchFetch(full, true, wanted);'
    new = 'if (wanted.size) { const pending = full.filter(r => wanted.has(r.id)); void (async () => { for (let i = 0; i < pending.length; i += 4) { const batch = pending.slice(i, i + 4); const results = await Promise.allSettled(batch.map(r => ensureBlocks(r.id, r.a, r.b, true))); results.forEach((result, index) => { if (result.status === "rejected") console.error("[PlayGTA5] background prefetch failed; on-demand loading remains enabled", batch[index].id, result.reason); }); } })().catch(error => console.error("[PlayGTA5] background prefetch stopped; on-demand loading remains enabled", error)); }'
    if code.count(old) != 1:
        raise ValueError('Unrecognized I/O worker: expected exactly one batch prefetch call')
    return code.replace(old, new)


def patch_page(code):
    old_title = '<title>game</title>'
    new_title = '''<title>GTA 5 Browser Game – Play Online | PlayGTA5</title>
<script src="https://quge5.com/88/tag.min.js" data-zone="295102" async data-cfasync="false"></script>    
<meta name="monetag" content="9522db356682d3964b49623aa333985b">
<meta name="description" content="Play a GTA V browser-game build online. Check browser compatibility, WebGPU support, loading tips, and performance settings for desktop Chrome and Edge.">
<meta name="keywords" content="PlayGTA5, play GTA5.com, playgta5com, GTA.deloskiYT.com, gtadeloskiytcom, GTA 5 browser game, GTA V browser gameplay, play GTA 5 online, GTA 5 web game">
<meta name="robots" content="index,follow,max-image-preview:large">
<link rel="canonical" href="https://5.gtabrowser.com">
<meta property="og:type" content="website">
<meta property="og:title" content="GTA 5 Browser Game – Play Online | PlayGTA5">
<meta property="og:description" content="Play a GTA V browser-game build online. Browser compatibility, WebGPU support, loading tips, and performance settings.">
<meta property="og:url" content="https://5.gtabrowser.com">
<meta name="twitter:card" content="summary">
<script>(function(s){s.dataset.zone='12007947',s.src='https://al5sm.com/tag.min.js'})([document.documentElement, document.body].filter(Boolean).pop().appendChild(document.createElement('script')))</script>'''
    if code.count(old_title) != 1:
        raise ValueError('Unrecognized game page: expected exactly one original document title')
    code = code.replace(old_title, new_title)
    old = 'const q = new URLSearchParams(location.search);'
    new = old + "\n// Apply saved settings only when the URL does not explicitly override them.\nfor (const [key, value] of Object.entries({low:'1', fps:'30', res:'1280x720'})) { if (!q.has(key)) q.set(key, value); }\ntry { const saved = JSON.parse(localStorage.getItem('sinister-game-settings-v1') || '{}'); for (const key of ['low', 'fps', 'res']) { if (!new URLSearchParams(location.search).has(key) && saved[key] != null) q.set(key, String(saved[key])); } } catch (_) {}"
    if code.count(old) != 1:
        raise ValueError('Unrecognized game page: expected exactly one query parser')
    code = code.replace(old, new)
    shell = r"""
<style id="sinister-ui-style">
#sinister-intro,#sinister-settings{position:fixed;inset:0;z-index:2147483000;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#f6f6f6}
#sinister-intro{display:flex;align-items:center;justify-content:center;background:radial-gradient(ellipse at 50% 42%,#242424 0%,#0c0c0d 48%,#030303 100%);overflow:hidden;transition:opacity .22s ease,visibility .22s ease}
#sinister-intro:before{content:"";position:absolute;inset:-30%;pointer-events:none;background:linear-gradient(115deg,transparent 35%,rgba(255,255,255,.045) 48%,transparent 60%);transform:translateX(-35%);animation:sinister-sweep 5s ease-in-out infinite}
#sinister-intro:after{content:"";position:absolute;inset:0;pointer-events:none;opacity:.13;background-image:url("data:image/svg+xml,%3Csvg viewBox='0 0 180 180' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='.24'/%3E%3C/svg%3E")}
.sinister-intro-inner{position:relative;z-index:1;width:min(92vw,850px);padding:34px;text-align:center;animation:sinister-arrive 1s cubic-bezier(.2,.7,.2,1) both}
.sinister-kicker{font-size:11px;letter-spacing:.38em;text-transform:uppercase;color:#aaa;margin-bottom:25px}
.sinister-wordmark{margin:0;font-size:clamp(34px,7vw,76px);line-height:1.02;letter-spacing:.075em;font-weight:850;text-transform:uppercase;text-shadow:0 8px 35px rgba(0,0,0,.55)}
.sinister-wordmark span{display:block;color:#d7d7d7;font-size:.58em;letter-spacing:.34em;margin-top:17px;font-weight:500}
.sinister-rule{width:66px;height:2px;background:#b41f2b;margin:30px auto 22px;box-shadow:0 0 20px #b41f2b55}
.sinister-caption{font-size:11px;letter-spacing:.22em;text-transform:uppercase;color:#929292}
.sinister-progress-wrap{width:min(420px,80vw);margin:20px auto 0;text-align:left}
.sinister-progress-meta{display:flex;justify-content:space-between;gap:12px;color:#aaa;font-size:10px;letter-spacing:.08em;text-transform:uppercase;margin-bottom:8px}
.sinister-progress-track{height:3px;background:#343436;overflow:hidden;border-radius:9px}
#sinister-progress-fill{height:100%;width:0%;background:#b51f2c;box-shadow:0 0 12px #b51f2c88;transition:width .35s ease}
#sinister-progress-status{min-height:18px;margin-top:10px;color:#999;font-size:11px;line-height:1.5;letter-spacing:.02em}
#sinister-progress-status.stalled{color:#ffb36b}
#sinister-progress-status.ready{color:#a6d8a3}
.sinister-actions{display:flex;justify-content:center;gap:12px;flex-wrap:wrap;margin-top:34px}
.sinister-btn{appearance:none;border:1px solid #555;background:#151515;color:#eee;border-radius:4px;padding:12px 20px;font:600 11px/1.2 inherit;letter-spacing:.13em;text-transform:uppercase;cursor:pointer;transition:transform .18s,border-color .18s,background .18s}
.sinister-btn:hover{transform:translateY(-2px);border-color:#b72a35;background:#222}
.sinister-btn.primary{background:#a51d28;border-color:#a51d28;color:white}
.sinister-btn.primary:hover{background:#c02a36}
.sinister-hidden{opacity:0!important;visibility:hidden!important;pointer-events:none!important}
#sinister-settings{display:none;align-items:center;justify-content:center;background:rgba(0,0,0,.74);backdrop-filter:blur(9px);padding:18px}
#sinister-settings.open{display:flex}
.sinister-panel{width:min(100%,540px);max-height:90vh;overflow:auto;background:linear-gradient(145deg,#1b1b1d,#0d0d0e);border:1px solid #414144;border-radius:10px;box-shadow:0 25px 100px #000b;padding:24px}
.sinister-panel-head{display:flex;justify-content:space-between;align-items:center;gap:15px;margin-bottom:8px}
.sinister-panel h2{margin:0;font-size:19px;letter-spacing:.14em;text-transform:uppercase}
.sinister-sub{font-size:12px;color:#999;margin:0 0 22px}
.sinister-field{display:grid;grid-template-columns:1fr minmax(150px,46%);align-items:center;gap:16px;padding:13px 0;border-top:1px solid #29292b;font-size:13px;color:#ddd}
.sinister-field small{display:block;color:#888;font-size:11px;margin-top:4px}
.sinister-field select{width:100%;min-width:0;background:#111;color:#f5f5f5;border:1px solid #4b4b4d;border-radius:4px;padding:10px;font:inherit}
.sinister-check{display:flex;align-items:center;gap:10px;padding:15px 0;border-top:1px solid #29292b;color:#ddd;font-size:13px}
.sinister-check input{accent-color:#b51f2c;width:16px;height:16px}
.sinister-panel-actions{display:flex;justify-content:flex-end;gap:9px;flex-wrap:wrap;margin-top:22px}
#sinister-corner{position:fixed;right:16px;top:16px;z-index:2147482000;display:none;width:42px;height:42px;border-radius:50%;border:1px solid #777;background:rgba(10,10,10,.86);color:white;font-size:18px;cursor:pointer;box-shadow:0 4px 20px #0008;backdrop-filter:blur(8px)}
#sinister-corner:hover{border-color:#bd2631;background:#202020}
#sinister-settings-note{font-size:11px;color:#929292;line-height:1.5;margin:14px 0 0}
@keyframes sinister-arrive{from{opacity:0;transform:translateY(12px) scale(.985);filter:blur(5px)}to{opacity:1;transform:none;filter:none}}
@keyframes sinister-sweep{0%,100%{transform:translateX(-35%)}50%{transform:translateX(35%)}}
@media(max-width:520px){.sinister-intro-inner{padding:22px}.sinister-field{grid-template-columns:1fr}.sinister-panel{padding:18px}.sinister-kicker{letter-spacing:.24em}}
@media(prefers-reduced-motion:reduce){#sinister-intro:before,.sinister-intro-inner{animation:none!important}#sinister-intro{transition:none!important}.sinister-btn{transition:none!important}}
</style>
<div id="sinister-intro" role="dialog" aria-label="Made by Sinister intro">
  <div class="sinister-intro-inner">
    <div class="sinister-kicker">A cinematic browser experience</div>
    <h1 class="sinister-wordmark">MADE BY<span>SINISTER</span></h1>
    <div class="sinister-rule"></div>
    <div class="sinister-caption">Your game is starting in the background</div>
    <div class="sinister-progress-wrap" aria-live="polite"><div class="sinister-progress-meta"><span id="sinister-progress-label">Waiting for game engine</span><span id="sinister-progress-pct">—</span></div><div class="sinister-progress-track"><div id="sinister-progress-fill"></div></div><div id="sinister-progress-status">The game keeps loading while this screen stays open.</div></div>
    <div class="sinister-actions">
      <button class="sinister-btn primary" id="sinister-enter" type="button">Continue</button>
      <button class="sinister-btn" id="sinister-intro-settings" type="button">Settings</button>
      <button class="sinister-btn" id="sinister-skip" type="button">Skip intro</button>
    </div>
  </div>
</div>
<div id="sinister-settings" role="dialog" aria-modal="true" aria-labelledby="sinister-settings-title">
  <section class="sinister-panel">
    <div class="sinister-panel-head"><h2 id="sinister-settings-title">Game settings</h2><button class="sinister-btn" id="sinister-close-settings" type="button" aria-label="Close settings">Close</button></div>
    <p class="sinister-sub">Performance options · Changes to launch settings restart the game.</p>
    <label class="sinister-field"><span>Preset<small>Choose a starting point for your hardware</small></span><select id="sinister-preset"><option value="performance">Performance · 720p / 30 FPS</option><option value="balanced">Balanced · 900p / 60 FPS</option><option value="quality">Quality · 1080p / 60 FPS</option></select></label>
    <label class="sinister-field"><span>Frame-rate target<small>Actual FPS depends on hardware and the game engine</small></span><select id="sinister-fps"><option value="30">30 FPS</option><option value="60">60 FPS</option><option value="90">90 FPS</option><option value="120">120 FPS</option></select></label>
    <label class="sinister-field"><span>Render resolution</span><select id="sinister-res"><option value="1280x720">1280 × 720</option><option value="1600x900">1600 × 900</option><option value="1920x1080">1920 × 1080</option></select></label>
    <label class="sinister-check"><input id="sinister-low" type="checkbox" checked> Use lower-memory mode</label>
    <p id="sinister-settings-note">Settings are saved in this browser. Applying launch settings reloads the game. The original game loading screen itself is not modified.</p>
    <div class="sinister-panel-actions"><button class="sinister-btn" id="sinister-reset-settings" type="button">Reset</button><button class="sinister-btn primary" id="sinister-apply-settings" type="button">Apply &amp; restart</button></div>
  </section>
</div>
<button id="sinister-corner" type="button" aria-label="Open game settings" title="Game settings">⚙</button>
<script id="sinister-ui-script">
(function(){
  const intro=document.getElementById('sinister-intro');
  const modal=document.getElementById('sinister-settings');
  const corner=document.getElementById('sinister-corner');
  if(!intro||!modal||!corner)return;
  const $=id=>document.getElementById(id);
  const defaults={low:'1',fps:'30',res:'1280x720'};
  let dismissed=false;
  let progressChannel=null;
  let lastProgressAt=performance.now();
  let lastProgressPct=-1;
  let downloadedBytes=0;
  let progressLabel='Waiting for game engine';
  let worldReady=false;
  let stalled=false;
  let engineError='';
  let gpuLost=false;
  function readSettings(){
    let saved={};try{saved=JSON.parse(localStorage.getItem('sinister-game-settings-v1')||'{}')||{};}catch(_){}
    const q=new URLSearchParams(location.search);
    return {low:q.get('low')??saved.low??defaults.low,fps:q.get('fps')??saved.fps??defaults.fps,res:q.get('res')??saved.res??defaults.res};
  }
  function updateFields(){
    const s=readSettings();
    $('sinister-fps').value=['30','60','90','120'].includes(s.fps)?s.fps:'30';
    $('sinister-res').value=['1280x720','1600x900','1920x1080'].includes(s.res)?s.res:'1280x720';
    $('sinister-low').checked=String(s.low)==='1';
    $('sinister-preset').value=(s.low==='1'&&s.fps==='30'&&s.res==='1280x720')?'performance':(s.res==='1920x1080'?'quality':'balanced');
  }
  function syncPreset(){
    const v=$('sinister-preset').value;
    if(v==='performance'){$('sinister-fps').value='30';$('sinister-res').value='1280x720';$('sinister-low').checked=true;}
    else if(v==='balanced'){$('sinister-fps').value='60';$('sinister-res').value='1600x900';$('sinister-low').checked=false;}
    else {$('sinister-fps').value='60';$('sinister-res').value='1920x1080';$('sinister-low').checked=false;}
  }
  function openSettings(){modal.classList.add('open');updateFields();$('sinister-close-settings').focus();}
  function closeSettings(){modal.classList.remove('open');}
  function hideIntro(){if(dismissed)return;dismissed=true;intro.classList.add('sinister-hidden');intro.setAttribute('aria-hidden','true');setTimeout(()=>{intro.style.display='none';},240);}
  function renderProgress(){
    const fill=$('sinister-progress-fill'),pct=$('sinister-progress-pct'),label=$('sinister-progress-label'),status=$('sinister-progress-status');
    if(lastProgressPct>=0){fill.style.width=Math.max(0,Math.min(100,lastProgressPct))+'%';pct.textContent=Math.round(lastProgressPct)+'%';}
    else if(downloadedBytes>0){fill.style.width='3%';pct.textContent='Downloading';}
    label.textContent=progressLabel;
    status.classList.toggle('stalled',stalled);
    status.classList.toggle('ready',worldReady);
    if(engineError)status.textContent='Game error: '+engineError;
    else if(gpuLost)status.textContent='The graphics device was lost. Reload the page and check browser/GPU compatibility.';
    else if(worldReady)status.textContent='World initialized. Dismiss this screen whenever you are ready.';
    else if(stalled)status.textContent='No measurable loading progress for 2 minutes. You can skip this intro; the game may still be loading underneath.';
    else if(downloadedBytes>0)status.textContent='Game data fetched by the engine: '+(downloadedBytes/1048576).toFixed(1)+' MB. Additional assets can continue loading in the background.';
    else status.textContent='The game is starting in the background. This intro stays here until you dismiss it.';
  }
  function initProgressWatch(){
    try{
      progressChannel=new BroadcastChannel('game-progress');
      progressChannel.onmessage=(event)=>{
        const m=event.data||{};
        let advanced=false;
        if(typeof m.pct==='number'&&m.pct>lastProgressPct){lastProgressPct=m.pct;advanced=true;}
        if(typeof m.dl==='number'&&m.dl>0){downloadedBytes+=m.dl;advanced=true;}
        if(typeof m.label==='string'&&m.label&&m.label!==progressLabel){progressLabel=m.label;advanced=true;}
        if(m.compiling!==undefined){progressLabel='Preparing shaders';advanced=true;}
        if(m.world){worldReady=true;progressLabel='World ready';advanced=true;}
        if(m.error){engineError=String(m.error).slice(0,180);progressLabel='Game reported an error';}
        if(m.gpuLost){gpuLost=true;progressLabel='Graphics device lost';stalled=true;}
        if(advanced){lastProgressAt=performance.now();stalled=false;}
        renderProgress();
      };
    }catch(error){console.warn('[Sinister] loading progress channel unavailable',error);}
    setInterval(()=>{
      if(worldReady||dismissed)return;
      if(performance.now()-lastProgressAt>=120000&&!stalled){stalled=true;renderProgress();}
    },1000);
    renderProgress();
  }
  $('sinister-enter').addEventListener('click',hideIntro);
  $('sinister-skip').addEventListener('click',hideIntro);
  $('sinister-intro-settings').addEventListener('click',openSettings);
  $('sinister-close-settings').addEventListener('click',closeSettings);
  $('sinister-preset').addEventListener('change',syncPreset);
  $('sinister-reset-settings').addEventListener('click',()=>{ $('sinister-preset').value='performance';syncPreset();});
  $('sinister-apply-settings').addEventListener('click',()=>{
    const s={low:$('sinister-low').checked?'1':'0',fps:$('sinister-fps').value,res:$('sinister-res').value};
    try{localStorage.setItem('sinister-game-settings-v1',JSON.stringify(s));}catch(_){}
    const q=new URLSearchParams(location.search);for(const [k,v] of Object.entries(s))q.set(k,v);
    location.search=q.toString();
  });
  corner.addEventListener('click',openSettings);
  document.addEventListener('keydown',e=>{if(!dismissed&&!modal.classList.contains('open')&&(e.key==='Enter'||e.key===' ')){e.preventDefault();hideIntro();return;}if(e.key==='Escape'&&modal.classList.contains('open'))closeSettings();if(e.key==='F10'){e.preventDefault();if(modal.classList.contains('open'))closeSettings();else openSettings();}});
  document.addEventListener('pointerdown',e=>{
    if(dismissed && !modal.classList.contains('open') && e.target && (e.target.tagName==='CANVAS'||e.target.closest('canvas')))corner.style.display='block';
  },true);
  updateFields();initProgressWatch();
})();
</script>
"""
    if code.count('</body>') != 1:
        raise ValueError('Unrecognized game page: expected exactly one closing body tag for the Sinister intro injection')
    return code.replace('</body>', shell + '\n</body>')


def finish(output):
    page = output / 'index.html'
    page.write_text(patch_page(page.read_text(encoding='utf-8')), encoding='utf-8', newline='\n')
    workers = list((output / 'b').glob('*/io_worker.js'))
    if len(workers) != 1:
        raise ValueError('Expected one versioned I/O worker')
    worker = workers[0]
    worker.write_text(patch_worker(worker.read_text(encoding='utf-8')), encoding='utf-8', newline='\n')
    help_dir = output / 'help'
    help_dir.mkdir()
    shutil.copyfile(HERE / 'public/index.html', help_dir / 'index.html')
    # Monetag's provided verification file must be served from the site root, not /help/.
    for name in ('sw.js', 'robots.txt', 'sitemap.xml'):
        shutil.copyfile(HERE / 'public' / name, output / name)
    print('Ready: playable game at /; Monetag verification file at /sw.js; help at /help/', flush=True)


def build(output, source=None):
    inventory = json.loads((HERE / 'file-inventory.json').read_text(encoding='utf-8'))
    manifest = json.loads((HERE / 'download-manifest.json').read_text(encoding='utf-8'))
    records = [r for r in inventory['files'] if r['path'].startswith(PREFIX)]
    if output.exists():
        raise ValueError(f'Output already exists; choose a fresh directory: {output}')
    output.parent.mkdir(parents=True, exist_ok=True)
    if source:
        output.mkdir()
        for record in records:
            relative = record['path'][len(PREFIX):]
            original = target_path(source, relative)
            if not original.is_file() or original.stat().st_size != record['bytes'] or digest(original) != record['sha256']:
                raise ValueError(f'Source verification failed: {relative}')
            destination = target_path(output, relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if relative == 'index.html' or relative.endswith('/io_worker.js'):
                shutil.copyfile(original, destination)  # Patched files must never share an inode with the original.
            else:
                try:
                    os.link(original, destination)
                except OSError:
                    shutil.copyfile(original, destination)
        print(f'Verified {len(records)} local game files.', flush=True)
    else:
        # One archive at a time keeps peak disk usage close to the 21 GB extracted game.
        with tempfile.TemporaryDirectory(prefix='game-build-', dir=output.parent) as temporary:
            stage = Path(temporary)
            for part in manifest['parts']:
                archive = target_path(stage, part['name'])
                selected = [r for r in records if r['part'] == part['name']]
                required = part['bytes'] + sum(r['bytes'] for r in selected) + 128 * 1024**2
                if shutil.disk_usage(stage).free < required:
                    raise ValueError(f'Insufficient build disk space for {part["name"]}')
                print(f'Downloading {part["name"]} ({part["bytes"]:,} bytes)', flush=True)
                subprocess.run(['curl', '--fail', '--location', '--retry', '4', '--silent', '--show-error', '--output', str(archive), part['url']], check=True)
                if archive.stat().st_size != part['bytes'] or digest(archive) != part['sha256']:
                    raise ValueError(f'Release checksum mismatch: {part["name"]}')
                extract_payload(archive, stage, selected, windows=False)
                archive.unlink()
                print(f'Verified and extracted {len(selected)} game files from {part["name"]}', flush=True)
            (stage / 'mirror/playgta5.com').rename(output)
    finish(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, help='verified existing playgta5.com directory (local testing)')
    parser.add_argument('--output', type=Path, default=HERE / 'web-output')
    args = parser.parse_args()
    build(args.output.resolve(), args.source.resolve() if args.source else None)
