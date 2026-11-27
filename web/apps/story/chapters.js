// Four optional WebGL chapter illustrations. Text and SVGs remain the fallback.
const stages=[...document.querySelectorAll('.chapter-scene')];
const toggle=document.querySelector('#motion-toggle');
const reduced=matchMedia('(prefers-reduced-motion: reduce)');
let disabled=reduced.matches||Boolean(navigator.connection?.saveData);
try { disabled ||= sessionStorage.getItem('interviewops-motion')==='off'; } catch {}
let epoch=0, threePromise;
const active=new Map();
const loadThree=()=>threePromise ||= import('../../node_modules/three/build/three.module.js');

async function mount(el){
  if(disabled || active.has(el))return;
  const version=epoch;
  active.set(el,{loading:true});
  let renderer;
  try{
    if(!document.createElement('canvas').getContext('webgl2')){active.delete(el);return;}
    const T=await loadThree();
    if(disabled || version!==epoch){active.delete(el);return;}
    renderer=new T.WebGLRenderer({antialias:true,alpha:true,powerPreference:'low-power'});
    renderer.outputColorSpace=T.SRGBColorSpace;renderer.toneMapping=T.ACESFilmicToneMapping;
    renderer.setPixelRatio(Math.min(devicePixelRatio,innerWidth<900?1.5:2));
    el.append(renderer.domElement);el.classList.add('scene-ready');
    const scene=new T.Scene(), camera=new T.PerspectiveCamera(36,1,.1,100);
    camera.position.set(5,4.5,12);camera.lookAt(0,0,0);
    scene.add(new T.HemisphereLight(0xd9e6ff,0x101422,2));
    const light=new T.DirectionalLight(0xc3d6ff,4);light.position.set(-4,6,5);scene.add(light);
    const accent=new T.PointLight(0x698eff,48,22);accent.position.set(3,1,4);scene.add(accent);
    const mat={metal:new T.MeshPhysicalMaterial({color:0xb2c0d9,metalness:.65,roughness:.3,clearcoat:.8}),blue:new T.MeshPhysicalMaterial({color:0x547fff,metalness:.35,roughness:.23,clearcoat:1}),dark:new T.MeshPhysicalMaterial({color:0x222d49,metalness:.7,roughness:.3}),warm:new T.MeshPhysicalMaterial({color:0xe7b9a4,metalness:.4,roughness:.3}),glass:new T.MeshPhysicalMaterial({color:0x7b9ff5,metalness:.22,roughness:.2,transparent:true,opacity:.65,depthWrite:false})};
    const geos=new Set(), own=g=>{geos.add(g);return g;};
    const group=new T.Group();scene.add(group);
    function rounded(w,h,d,r=.15){
      const s=new T.Shape();s.moveTo(-w/2+r,-h/2);s.lineTo(w/2-r,-h/2);s.quadraticCurveTo(w/2,-h/2,w/2,-h/2+r);s.lineTo(w/2,h/2-r);s.quadraticCurveTo(w/2,h/2,w/2-r,h/2);s.lineTo(-w/2+r,h/2);s.quadraticCurveTo(-w/2,h/2,-w/2,h/2-r);s.lineTo(-w/2,-h/2+r);s.quadraticCurveTo(-w/2,-h/2,-w/2+r,-h/2);
      const g=own(new T.ExtrudeGeometry(s,{depth:d,bevelEnabled:true,bevelSize:.04,bevelThickness:.04,bevelSegments:2,curveSegments:6}));g.translate(0,0,-d/2);return g;
    }
    function box(w,h,d,m,x,y,z){const mesh=new T.Mesh(rounded(w,h,d),m);mesh.position.set(x,y,z);group.add(mesh);return mesh;}
    function ring(radius,tube,m,x,y,z){const mesh=new T.Mesh(own(new T.TorusGeometry(radius,tube,12,64)),m);mesh.position.set(x,y,z);group.add(mesh);return mesh;}
    let update=()=>{};
    if(el.dataset.chapter==='anatomy'){
      box(5,.24,1,mat.dark,0,-1.15,0);
      const a=box(1.6,.32,.85,mat.blue,-1.45,.8,.1),b=box(1.6,.32,.85,mat.warm,1.45,.15,.1);
      update=(p,t)=>{a.position.x=-1.45+.75*p;b.position.x=1.45-.75*p;a.position.y=.8+Math.sin(t*.6)*.045;b.position.y=.15+Math.sin(t*.6+1)*.045;};
    } else if(el.dataset.chapter==='locks'){
      for(let i=0;i<3;i++) box(1.55,.34,1.05,mat.metal,(i-1)*1.9,0,0);
      const order=box(.18,1.3,.26,mat.blue,-1.9,.85,.45);
      update=(p,t)=>{order.position.x=-1.9+3.8*p;order.position.y=.85+Math.sin(t*.5)*.035;};
    } else if(el.dataset.chapter==='constraints'){
      box(5,.22,1,mat.dark,0,-.9,0);
      box(2,.42,.9,mat.blue,-1,0,0);
      const next=box(2,.42,.9,mat.metal,1.5,0,0);
      update=(p)=>{next.position.x=1.5-.5*p;};
    } else {
      const a=ring(1.15,.09,mat.blue,-.65,.3,0),b=ring(1.15,.09,mat.warm,.65,-.3,.1);
      a.rotation.set(.25,.4,.3);b.rotation.set(-.2,-.4,-.3);
      update=(p,t)=>{a.rotation.z=.3+.1*p+Math.sin(t*.3)*.025;b.rotation.z=-.3-.1*p-Math.sin(t*.3)*.025;};
    }
    const initial=el.parentElement.getBoundingClientRect();
    let visible=initial.top<innerHeight+150&&initial.bottom>-150,raf=0,last=performance.now(),time=0;
    function draw(now){raf=0;if(!visible||document.hidden)return;time+=Math.min(.05,(now-last)/1000);last=now;
      const r=el.getBoundingClientRect();const p=Math.max(0,Math.min(1,(innerHeight-r.top)/(innerHeight+r.height)));
      update(p,time);group.rotation.y=Math.sin(time*.2)*.035;renderer.render(scene,camera);raf=requestAnimationFrame(draw);
    }
    function schedule(){if(visible&&!document.hidden&&!raf){last=performance.now();raf=requestAnimationFrame(draw);}}
    function resize(){const r=el.getBoundingClientRect();if(!r.width||!r.height)return;renderer.setSize(r.width,r.height,false);camera.aspect=r.width/r.height;camera.position.z=innerWidth<600?15:12;camera.updateProjectionMatrix();schedule();}
    const ro=new ResizeObserver(resize);ro.observe(el);
    document.addEventListener('visibilitychange',schedule);
    const lost=e=>{e.preventDefault();active.get(el)?.dispose?.();active.delete(el);};
    renderer.domElement.addEventListener('webglcontextlost',lost);
    const state={setVisible(v){visible=v;if(v)schedule();else{cancelAnimationFrame(raf);raf=0;}},dispose(){cancelAnimationFrame(raf);ro.disconnect();document.removeEventListener('visibilitychange',schedule);renderer.domElement.removeEventListener('webglcontextlost',lost);geos.forEach(g=>g.dispose());Object.values(mat).forEach(m=>m.dispose());renderer.dispose();renderer.domElement.remove();el.classList.remove('scene-ready');}};
    active.set(el,state);resize();schedule();
  }catch(error){renderer?.dispose();renderer?.domElement.remove();el.classList.remove('scene-ready');active.delete(el);console.warn('Chapter scene unavailable; showing still.',error);}
}
const observer=new IntersectionObserver(entries=>{for(const e of entries){const el=e.target.querySelector('.chapter-scene');if(!el)continue;const state=active.get(el);if(e.isIntersecting){if(state&&!state.loading)state.setVisible(true);else if(!state)mount(el);}else if(state&&!state.loading)state.setVisible(false);}},{rootMargin:'150px'});
stages.forEach(el=>observer.observe(el.parentElement));
function stopAll(){epoch++;for(const state of active.values())if(!state.loading)state.dispose();active.clear();}
toggle?.addEventListener('click',()=>{disabled=toggle.getAttribute('aria-pressed')==='true';stopAll();if(!disabled)stages.forEach(el=>{const r=el.parentElement.getBoundingClientRect();if(r.top<innerHeight+150&&r.bottom>-150)mount(el);});});
reduced.addEventListener('change',e=>{if(e.matches){disabled=true;stopAll();}});
