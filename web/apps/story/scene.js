// Progressive enhancement. The authored narrative and SVG stills remain available
// whenever animation is disabled or the device cannot run WebGL.
const stage = document.querySelector('#opening-stage');
const container = stage?.querySelector('.scene-canvas');
const toggle = document.querySelector('#motion-toggle');
const reduced = matchMedia('(prefers-reduced-motion: reduce)');
let cleanup = () => {};
let generation = 0;
let stopped = reduced.matches || Boolean(navigator.connection?.saveData);
try { stopped ||= sessionStorage.getItem('interviewops-motion') === 'off'; } catch {}

async function start() {
  if (!stage || !container || !toggle || stopped || reduced.matches) return;
  const request = ++generation;
  let renderer;
  try {
    if (!document.createElement('canvas').getContext('webgl2')) return;
    const THREE = await import('../../node_modules/three/build/three.module.js');
    if (request !== generation || stopped || reduced.matches) return;
    renderer = new THREE.WebGLRenderer({antialias:true, alpha:true, powerPreference:'high-performance'});
    renderer.setPixelRatio(Math.min(devicePixelRatio, innerWidth < 900 ? 1.5 : 2));
    renderer.setClearColor(0x000000,0);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.15;
    renderer.autoClear = false;
    renderer.domElement.style.maskImage='radial-gradient(ellipse 74% 72% at 50% 50%, #000 45%, transparent 100%)';
    renderer.domElement.style.webkitMaskImage=renderer.domElement.style.maskImage;
    container.append(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(36,1,.1,100);
    camera.position.set(0,3.1,13.8); camera.lookAt(0,.05,0);
    scene.add(new THREE.HemisphereLight(0xdde5ff,0x20202d,2.1));
    const key = new THREE.DirectionalLight(0xe5ecff,4.0); key.position.set(-4,8,7); scene.add(key);
    const rim = new THREE.DirectionalLight(0x9cb5ff,3.4); rim.position.set(6,4,-8); scene.add(rim);
    const warm = new THREE.PointLight(0xffdfc7,50,28); warm.position.set(-5,2,4); scene.add(warm);

    const bgScene = new THREE.Scene();
    const bgCamera = new THREE.OrthographicCamera(-1,1,1,-1,0,1);
    const fluid = new THREE.ShaderMaterial({
      uniforms:{uTime:{value:0},uProgress:{value:0},uAspect:{value:1}},
      vertexShader:`varying vec2 vUv; void main(){vUv=uv;gl_Position=vec4(position.xy,0.0,1.0);}`,
      fragmentShader:`
        varying vec2 vUv; uniform float uTime; uniform float uProgress; uniform float uAspect;
        void main(){
          vec2 p=vUv*2.0-1.0; p.x*=uAspect;
          float t=uTime*.09;
          float f=sin(p.x*1.25+p.y*2.3+t)+.55*sin(p.x*2.2-p.y*1.1-t*.8);
          float sweep=1.0-smoothstep(-.6,.52,p.y+.22*sin(p.x*1.6+t)+f*.08-uProgress*.2);
          float glow=exp(-2.0*length(vec2((p.x-.42)*.8,p.y+.1+.12*sin(t))));
          vec3 base=vec3(.012,.023,.055);
          vec3 indigo=vec3(.025,.065,.19);
          vec3 pearl=vec3(.26,.34,.50);
          vec3 col=mix(base,indigo,sweep*.70)+pearl*glow*.23;
          float fold=pow(max(0.0,1.0-abs(p.y+.35*sin(p.x*1.45+t)-.14)*3.8),6.0);
          col+=vec3(.23,.36,.70)*fold*.42;
          float strand=sin(p.y*19.0+sin(p.x*2.5+t)*2.3+f)*.5+.5;
          float sheet=smoothstep(.42,.72,strand)*(1.0-smoothstep(.22,.85,abs(p.y+.44+.24*sin(p.x*1.4+t))));
          col+=vec3(.04,.12,.30)*sheet;
          gl_FragColor=vec4(col,1.0);
        }`
    });
    const geometries = new Set();
    const own = g => { geometries.add(g); return g; };
    bgScene.add(new THREE.Mesh(own(new THREE.PlaneGeometry(2,2)),fluid));

    const materials = {
      metal:new THREE.MeshPhysicalMaterial({color:0x9caac5,metalness:.78,roughness:.26,clearcoat:1,clearcoatRoughness:.16}),
      dark:new THREE.MeshPhysicalMaterial({color:0x171f38,metalness:.72,roughness:.22,clearcoat:1}),
      blue:new THREE.MeshPhysicalMaterial({color:0x416ef4,metalness:.4,roughness:.18,clearcoat:1,clearcoatRoughness:.14}),
      silver:new THREE.MeshPhysicalMaterial({color:0xc7d3e9,metalness:.6,roughness:.22,clearcoat:1}),
      glass:new THREE.MeshPhysicalMaterial({color:0x527ef8,metalness:.35,roughness:.16,transparent:true,opacity:.74,depthWrite:false,clearcoat:1}),
      glassWarm:new THREE.MeshPhysicalMaterial({color:0x99afd4,metalness:.48,roughness:.19,transparent:true,opacity:.72,depthWrite:false,clearcoat:1}),
      ribbon:new THREE.MeshPhysicalMaterial({color:0x3463dd,metalness:.35,roughness:.26,clearcoat:1,transparent:true,opacity:.78}),
    };
    // Rounded extrusions make the objects feel machined without external models.
    function roundedBox(w,h,d,r=.18) {
      const s=new THREE.Shape();
      s.moveTo(-w/2+r,-h/2); s.lineTo(w/2-r,-h/2); s.quadraticCurveTo(w/2,-h/2,w/2,-h/2+r);
      s.lineTo(w/2,h/2-r); s.quadraticCurveTo(w/2,h/2,w/2-r,h/2);
      s.lineTo(-w/2+r,h/2); s.quadraticCurveTo(-w/2,h/2,-w/2,h/2-r);
      s.lineTo(-w/2,-h/2+r); s.quadraticCurveTo(-w/2,-h/2,-w/2+r,-h/2);
      const geo=own(new THREE.ExtrudeGeometry(s,{depth:d,bevelEnabled:true,bevelThickness:.055,bevelSize:.055,bevelSegments:3,curveSegments:10,steps:1}));
      geo.translate(0,0,-d/2); return geo;
    }
    function mesh(geometry,material,x,y,z,parent=scene){const m=new THREE.Mesh(geometry,material);m.position.set(x,y,z);parent.add(m);return m;}
    const world=new THREE.Group(); scene.add(world);
    // Two independent request plates meet at one central interval.
    function roundedFrame(w,h,depth,corner,stroke){
      const outer=new THREE.Shape(); const inner=new THREE.Path();
      function path(p,x,y,w,h,r){p.moveTo(x+r,y);p.lineTo(x+w-r,y);p.quadraticCurveTo(x+w,y,x+w,y+r);p.lineTo(x+w,y+h-r);p.quadraticCurveTo(x+w,y+h,x+w-r,y+h);p.lineTo(x+r,y+h);p.quadraticCurveTo(x,y+h,x,y+h-r);p.lineTo(x,y+r);p.quadraticCurveTo(x,y,x+r,y);}
      path(outer,-w/2,-h/2,w,h,corner);path(inner,-w/2+stroke,-h/2+stroke,w-2*stroke,h-2*stroke,corner-stroke);
      outer.holes.push(inner);
      const g=own(new THREE.ExtrudeGeometry(outer,{depth,bevelEnabled:true,bevelThickness:.035,bevelSize:.035,bevelSegments:3,curveSegments:10}));g.translate(0,0,-depth/2);return g;
    }
    const plateGeo=roundedFrame(2.6,1.72,.18,.24,.075);
    const insetGeo=roundedBox(2.43,1.55,.13,.21);
    const requestA=new THREE.Group(),requestB=new THREE.Group();
    world.add(requestA,requestB);
    mesh(plateGeo,materials.metal,0,0,0,requestA);
    mesh(insetGeo,materials.glass,0,0,.10,requestA).renderOrder=2;
    mesh(plateGeo,materials.metal,0,0,0,requestB);
    mesh(insetGeo,materials.glassWarm,0,0,.10,requestB).renderOrder=2;
    // The marks are abstract interval bars, not fabricated product UI.
    const markGeo=roundedBox(.84,.13,.05,.05);
    mesh(markGeo,materials.blue,-.55,-.53,.23,requestA);
    mesh(markGeo,materials.silver,.55,-.53,.23,requestB);
    requestA.position.set(-2.2,.35,0); requestB.position.set(2.2,.35,0);
    requestA.rotation.set(.05,.30,-.14); requestB.rotation.set(.05,-.30,.14);
    const base=mesh(own(new THREE.CylinderGeometry(1.18,1.28,.3,64)),materials.dark,0,-1.42,0,world);
    const baseRim=mesh(own(new THREE.TorusGeometry(1.12,.035,12,96)),materials.metal,0,-1.25,0,world);baseRim.rotation.x=Math.PI/2;
    const windowMesh=mesh(roundedBox(1.62,.28,.78,.14),materials.blue,0,-1.16,0,world);
    // Silk-like wave surfaces catch grazing light behind the request plates.
    const fabricMaterial=new THREE.MeshPhysicalMaterial({color:0x102958,metalness:.08,roughness:.9,clearcoat:.05,side:THREE.DoubleSide,transparent:true,opacity:.46,depthWrite:false});
    const fabricEdge=new THREE.MeshPhysicalMaterial({color:0x1a3a7d,metalness:.06,roughness:.9,clearcoat:.05,side:THREE.DoubleSide,transparent:true,opacity:.35,depthWrite:false});
    materials.fabric=fabricMaterial;materials.fabricEdge=fabricEdge;
    function fabric(y,z,material,phase){
      const g=own(new THREE.PlaneGeometry(10,2.8,72,20));
      const original=new Float32Array(g.attributes.position.array);
      const m=new THREE.Mesh(g,material);m.position.set(0,y,z);m.rotation.z=-.08;world.add(m);
      return {geometry:g,original,phase};
    }
    const fabrics=[fabric(-2.55,-2.5,fabricMaterial,0),fabric(-3.05,-3.1,fabricEdge,1.7)];
    function ripple(time){
      for(const item of fabrics){
        const p=item.geometry.attributes.position,o=item.original;
        for(let i=0;i<p.count;i++){
          const x=o[i*3], y=o[i*3+1];
          const wave=Math.sin(x*.95+y*1.7+time*.27+item.phase);
          p.setXYZ(i,x,y+wave*.08,Math.sin(x*.75-y*.7+time*.20+item.phase)*.15+wave*.06);
        }
        p.needsUpdate=true;item.geometry.computeVertexNormals();
      }
    }

    let frame=0,visible=false,last=performance.now(),elapsed=0;
    function progress(){
      const r=stage.getBoundingClientRect();
      return Math.max(0,Math.min(1,(innerHeight*.86-r.top)/(innerHeight*.85+r.height*.6)));
    }
    function render(now){
      frame=0; if(!visible || document.hidden)return;
      const dt=Math.min(.05,(now-last)/1000); last=now; elapsed+=dt;
      const p=progress(); fluid.uniforms.uTime.value=elapsed; fluid.uniforms.uProgress.value=p; ripple(elapsed);
      world.rotation.y=Math.sin(elapsed*.25)*.025+p*.04;
      world.rotation.z=.025*Math.sin(elapsed*.19);
      requestA.position.x=-2.2+.46*p; requestB.position.x=2.2-.46*p;
      requestA.position.y=.35+Math.sin(elapsed*.65)*.07;
      requestB.position.y=.35+Math.sin(elapsed*.65+1.4)*.07;
      requestA.rotation.z=-.14+Math.sin(elapsed*.4)*.025;
      requestB.rotation.z=.14+Math.sin(elapsed*.4+2)*.025;
      windowMesh.scale.x=.92+.08*p;
      renderer.clear(); renderer.render(bgScene,bgCamera); renderer.clearDepth(); renderer.render(scene,camera);
      frame=requestAnimationFrame(render);
    }
    function schedule(){if(visible&&!document.hidden&&!frame){last=performance.now();frame=requestAnimationFrame(render);}}
    function resize(){
      const {width,height}=container.getBoundingClientRect(); if(!width||!height)return;
      renderer.setPixelRatio(Math.min(devicePixelRatio,innerWidth<900?1.5:2));
      renderer.setSize(width,height,false); camera.aspect=width/height;
      // Keep the complete object inside portrait frames.
      camera.position.set(0,3.1,innerWidth<600?16.5:13.8);camera.lookAt(0,.05,0);camera.updateProjectionMatrix();
      fluid.uniforms.uAspect.value=Math.min(2.2,width/height);schedule();
    }
    const observer=new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;if(visible)schedule();else{cancelAnimationFrame(frame);frame=0;}},{rootMargin:'100px'});
    observer.observe(stage); const ro=new ResizeObserver(resize);ro.observe(container);
    addEventListener('scroll',schedule,{passive:true});document.addEventListener('visibilitychange',schedule);
    const lost=e=>{e.preventDefault();cleanup();};renderer.domElement.addEventListener('webglcontextlost',lost);
    cleanup=()=>{
      generation++;observer.disconnect();ro.disconnect();removeEventListener('scroll',schedule);document.removeEventListener('visibilitychange',schedule);
      cancelAnimationFrame(frame);renderer.domElement.removeEventListener('webglcontextlost',lost);
      geometries.forEach(g=>g.dispose());Object.values(materials).forEach(m=>m.dispose());fluid.dispose();
      renderer.dispose();renderer.domElement.remove();stage.classList.remove('scene-ready');cleanup=()=>{};
    };
    stage.classList.add('scene-ready');resize();schedule();
  } catch(error) {
    renderer?.dispose();renderer?.domElement.remove();stage.classList.remove('scene-ready');
    console.warn('Interactive scene unavailable; showing the still.',error);
  }
}
if(stage&&toggle){
  function updateButton(){toggle.setAttribute('aria-pressed',String(stopped));toggle.textContent=stopped?'Motion on':'Motion off';}
  toggle.addEventListener('click',()=>{stopped=!stopped;++generation;try{sessionStorage.setItem('interviewops-motion',stopped?'off':'on');}catch{}cleanup();if(!stopped)start();updateButton();});
  reduced.addEventListener('change',e=>{if(e.matches){++generation;cleanup();stopped=true;updateButton();}});
  updateButton();start();
}

import("./chapters.js").catch(() => {});
