// Shared, lazy-loaded crop: callers own persistence. Never overwrite original images.
import Cropper from 'cropperjs';
const MAX_BYTES = 20 * 1024 * 1024;
const MAX_PIXELS = 60_000_000;
const TEMPLATE = [
  '<cropper-canvas background>',
  '<cropper-image initial-fit="contain" translatable scalable></cropper-image>',
  '<cropper-shade></cropper-shade>',
  '<cropper-selection initial-coverage="1" movable resizable keyboard outlined>',
  '<cropper-grid role="grid" bordered covered></cropper-grid>',
  '<cropper-crosshair centered></cropper-crosshair>',
  '<cropper-handle action="move" theme-color="rgba(255,255,255,.07)"></cropper-handle>',
  ...['nw','ne','sw','se'].map(c => '<cropper-handle action="'+c+'-resize" theme-color="#fff"></cropper-handle>'),
  '</cropper-selection></cropper-canvas>',
].join('');
const CSS = [
  '.lantern-crop-dialog{width:min(96vw,1180px);max-height:96dvh;box-sizing:border-box;border:1px solid #526981;border-radius:12px;background:#101a28;color:#f3f7fa;padding:14px;overflow:auto;font:14px/1.5 system-ui,sans-serif}',
  '.lantern-crop-dialog::backdrop{background:rgba(0,0,0,.86)}',
  '.lantern-crop-dialog *{box-sizing:border-box}',
  '.lantern-crop-dialog h2{margin:0 0 6px;font-size:18px}',
  '.lantern-crop-tip{margin:0 0 12px;color:#b9cad9}',
  '.lantern-crop-stage{position:relative;display:block;width:100%;height:min(63dvh,680px);min-height:180px;background:#070b10;overflow:hidden;border:1px solid #526981;touch-action:none}',
  '.lantern-crop-stage cropper-canvas{display:block;width:100%;height:100%}',
  '.lantern-crop-paste-layer{position:absolute;z-index:30;border:2px solid #ffd178;border-radius:4px;cursor:move;touch-action:none;user-select:none;box-shadow:0 0 0 1px rgba(0,0,0,.55)}',
  '.lantern-crop-paste-layer>img{display:block;width:100%;height:100%;object-fit:fill;pointer-events:none}',
  '.lantern-crop-paste-resize{position:absolute;right:-9px;bottom:-9px;width:18px;height:18px;border:2px solid #101a28;background:#ffd178;cursor:nwse-resize;padding:0!important;min-height:0!important}',
  '.lantern-crop-paste-remove{position:absolute;right:-11px;top:-11px;width:22px;height:22px;border-radius:50%!important;padding:0!important;min-height:0!important;background:#7d2632!important;line-height:18px}',
  '.lantern-crop-actions{display:flex;align-items:center;justify-content:flex-end;gap:8px;flex-wrap:wrap;margin-top:12px}',
  '.lantern-crop-actions button{border:1px solid #536a83;border-radius:8px;background:#263748;color:#fff;padding:7px 12px;font:inherit;cursor:pointer;min-height:36px}',
  '.lantern-crop-actions button.primary{background:#337b62;border-color:#44a885}',
  '.lantern-crop-actions button.danger{background:#7d2632;border-color:#b94b5b}',
  '.lantern-crop-actions button:disabled{opacity:.6;cursor:progress}',
  '.lantern-crop-size{font:12px/1.4 ui-monospace,monospace;color:#cfe0ed;margin-right:auto}',
  '.lantern-crop-status{min-height:20px;margin-top:8px;color:#ffce80}',
  '.lantern-crop-stage cropper-handle:focus-visible{outline:2px solid #ffd178;outline-offset:2px}',
  '@media(pointer:coarse){.lantern-crop-stage cropper-handle[action$="-resize"]{width:32px!important;height:32px!important}}',
  '@media(max-width:650px){.lantern-crop-dialog{padding:8px}.lantern-crop-stage{height:56dvh}.lantern-crop-actions button{padding:7px 8px}}'
].join('\n');
let styleInstalled = false;
function ensureStyles() {
  if (styleInstalled && document.getElementById('lantern-crop-css')) return;
  const style=document.createElement('style');
  style.id='lantern-crop-css';style.textContent=CSS;document.head.append(style);
  styleInstalled=true;
}
function detectFormat(bytes) {
  const b=new Uint8Array(bytes), is=(at,s)=>[...s].every((c,i)=>b[at+i]===c.charCodeAt(0));
  if (b.length>=3 && b[0]===255&&b[1]===216&&b[2]===255) return 'image/jpeg';
  if (b.length>=24 && b[0]===137&&is(1,'PNG')) {
    const view=new DataView(b.buffer,b.byteOffset,b.byteLength);
    let pos=8;
    while(pos+8<=b.length) {
      const len=view.getUint32(pos),kind=String.fromCharCode(...b.subarray(pos+4,pos+8));
      if(kind==='acTL')throw Error('Animated PNG is unsupported.');
      // APNG acTL is required before IDAT. The IDAT data need not fit in our header.
      if(kind==='IDAT'||kind==='IEND')return 'image/png';
      if(len>b.length-pos-12)throw Error('PNG header exceeds the animation inspection limit.');
      pos+=12+len;
    }
    throw Error('Cannot verify the PNG animation header.');
  }
  if (b.length>=21&&is(0,'RIFF')&&is(8,'WEBP')) {
    if((is(12,'VP8X')&&(b[20]&2))||is(12,'ANIM'))
      throw Error('Animated WebP is unsupported.');
    if (is(12,'VP8L')) {
      // VP8L's alpha_is_used is bit 28 of its packed lossless header.
      // Lossless WebP is not necessarily transparent; avoid needless PNG.
      if(b.length<25||b[20]!==0x2f)throw Error('Invalid lossless WebP header.');
      const info=(b[21]|(b[22]<<8)|(b[23]<<16)|(b[24]<<24))>>>0;
      return info&0x10000000?'image/webp-alpha':'image/webp';
    }
    return is(12,'VP8X')&&(b[20]&16)?'image/webp-alpha':'image/webp';
  }
  if(b.length>=2&&is(0,'BM'))return 'image/bmp';
  throw Error('Crop supports static JPEG, PNG, WebP and BMP only.');
}
async function sourceFormat(url,signal) {
  const response=await fetch(url,{headers:{Range:'bytes=0-65535'},credentials:'same-origin',signal});
  if(!response.ok)throw Error('Cannot read image header: HTTP '+response.status);
  if(response.status!==206 && Number(response.headers.get('Content-Length')||0)>65536)
    throw Error('The server does not support bounded image header inspection.');
  const reader=response.body?.getReader();
  if(!reader)throw Error('Image header is unavailable.');
  const data=new Uint8Array(65536);
  let n=0;
  try {
    while(n<data.length) {
      const {done,value}=await reader.read();
      if(done)break;
      const size=Math.min(value.length,data.length-n);
      data.set(value.subarray(0,size),n);n+=size;
    }
  } finally {await reader.cancel().catch(()=>{});}
  return detectFormat(data.subarray(0,n));
}
function selectedPixels(selection,image,w,h) {
  const [a,b,c,d,e,f]=image.$getTransform();
  if(![a,b,c,d,e,f].every(Number.isFinite)||a<=0||d<=0||Math.abs(b)>1e-6||Math.abs(c)>1e-6)
    throw Error('Unsupported image transform; reset zoom.');
  // Cropper-image transforms around its CENTER, not the top-left origin.
  // The matrix translation alone is therefore not an image origin.
  // Use the rendered image/canvas rectangles to invert actual display
  // geometry (including centering, zoom and pan) into source pixels.
  const canvas=image.closest('cropper-canvas');
  if(!canvas)throw Error('Crop image canvas is unavailable.');
  const area=canvas.getBoundingClientRect();
  const img=image.getBoundingClientRect();
  if(!area.width||!area.height||!img.width||!img.height)throw Error('Image is not laid out.');
  const scaleX=canvas.clientWidth/area.width,scaleY=canvas.clientHeight/area.height;
  const left=(img.left-area.left)*scaleX,top=(img.top-area.top)*scaleY;
  const pxWidth=img.width*scaleX/w,pxHeight=img.height*scaleY/h;
  const clamp=(n,max)=>Math.max(0,Math.min(max,Math.round(n)));
  const x=clamp((selection.x-left)/pxWidth,w),y=clamp((selection.y-top)/pxHeight,h);
  const right=clamp((selection.x+selection.width-left)/pxWidth,w);
  const bottom=clamp((selection.y+selection.height-top)/pxHeight,h);
  if(right<=x||bottom<=y)throw Error('Choose a crop of at least one pixel.');
  return {x,y,width:right-x,height:bottom-y};
}
export function imageExtension(type) {
  if(type==='image/jpeg')return 'jpg';
  if(type==='image/png')return 'png';
  if(type==='image/webp')return 'webp';
  throw Error('Unsupported encoded format: '+type);
}
function toBlob(canvas,type,quality) {
  return new Promise((resolve,reject)=>{
    try {canvas.toBlob(b=>b?resolve(b):reject(Error('Encoder returned no image.')),type,quality);}
    catch(e){reject(e);}
  });
}
export async function openCrop({src,name='image',signal,allowOverwrite=false,preferredAction='copy'}={}) {
  if(!src)throw Error('Image URL missing.');
  const url=new URL(src,location.href);
  if(url.origin!==location.origin)throw Error('Only local images can be cropped.');
  if(signal?.aborted)return null;
  ensureStyles();
  const abort=new AbortController();
  const abortParent=()=>abort.abort();
  signal?.addEventListener('abort',abortParent,{once:true});
  const dialog=document.createElement('dialog');
  dialog.className='lantern-crop-dialog';
  dialog.setAttribute('aria-label','Crop image');
  const heading=document.createElement('h2');heading.textContent='Crop image — '+name;
  const tip=document.createElement('p');tip.className='lantern-crop-tip';
  tip.textContent='Drag any corner to resize, or drag inside to move. Zoom with +/− or the mouse wheel. Ctrl+V pastes an image layer; drag it to move and drag its corner to resize.';
  const stage=document.createElement('div');stage.className='lantern-crop-stage';
  const actions=document.createElement('div');actions.className='lantern-crop-actions';
  const measure=document.createElement('span');measure.className='lantern-crop-size';measure.setAttribute('aria-live','polite');actions.append(measure);
  const button=(label,klass='')=>{
    const b=document.createElement('button');b.type='button';b.textContent=label;b.className=klass;actions.append(b);return b;
  };
  const zoomOut=button('−'),zoomIn=button('+'),reset=button('Reset');
  const cancel=button('Cancel');
  const apply=allowOverwrite?null:button('Apply crop','primary');
  const saveCopy=allowOverwrite?button('Save cropped copy',preferredAction==='copy'?'primary':''):null;
  const overwrite=allowOverwrite?button('Overwrite original',preferredAction==='overwrite'?'primary danger':'danger'):null;
  const status=document.createElement('div');status.className='lantern-crop-status';status.setAttribute('role','status');
  dialog.append(heading,tip,stage,actions,status);document.body.append(dialog);dialog.showModal();
  return new Promise(resolve=>{
    let cropper,selection,cropperImage,source,format,done=false,exporting=false,frame=0;
    const pasteLayers=[];
    const cropButtons=[apply,saveCopy,overwrite].filter(Boolean);
    const finish=result=>{
      if(done)return;done=true;abort.abort();signal?.removeEventListener('abort',abortParent);
      if(frame)cancelAnimationFrame(frame);
      for(const layer of pasteLayers) URL.revokeObjectURL(layer.url);
      cropper?.destroy();dialog.close();dialog.remove();resolve(result);
    };
    abort.signal.addEventListener('abort',()=>finish(null),{once:true});
    const cancelCrop=()=>abort.abort();
    cancel.addEventListener('click',cancelCrop);
    dialog.addEventListener('cancel',e=>{e.preventDefault();e.stopPropagation();cancelCrop();});
    dialog.addEventListener('keydown',e=>{
      if(e.key==='Escape'){e.preventDefault();e.stopPropagation();cancelCrop();return;}
      if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key))return;
      e.preventDefault();e.stopPropagation();
      if(!selection||!cropperImage)return;
      const focus=e.target;
      if(!focus.matches?.('cropper-selection,cropper-handle') &&
         !focus.closest?.('cropper-selection'))return;
      const dir=e.key==='ArrowLeft'?[-1,0]:e.key==='ArrowRight'?[1,0]:e.key==='ArrowUp'?[0,-1]:[0,1];
      const step=(e.shiftKey?10:1)*Math.abs(cropperImage.$getTransform()[0]);
      const action=e.target.closest?.('cropper-handle')?.getAttribute('action');
      if(action?.endsWith('-resize'))selection.$resize(action,dir[0]*step,dir[1]*step);
      else selection.$move(dir[0]*step,dir[1]*step);
    });
    // The viewer listens for keyboard navigation on document.
    dialog.addEventListener('touchend',e=>e.stopPropagation(),{passive:true});
    const selectionBounds=()=>{
      if(!selection)return null;
      const r=selection.getBoundingClientRect(),base=stage.getBoundingClientRect();
      if(!r.width||!r.height)return null;
      return {left:r.left-base.left,top:r.top-base.top,width:r.width,height:r.height};
    };
    // CropperJS bounds selections against the canvas, not the image. Keep
    // the white rectangle entirely inside the *rendered* image (also after
    // zoom/pan); the pasted layer already follows this same containment rule.
    const imageBounds=()=>{
      if(!cropperImage)return null;
      const canvas=cropperImage.closest('cropper-canvas');
      const outer=canvas?.getBoundingClientRect();
      const img=cropperImage.getBoundingClientRect();
      if(!outer?.width||!outer.height||!img.width||!img.height)return null;
      const scaleX=canvas.clientWidth/outer.width,scaleY=canvas.clientHeight/outer.height;
      return {x:(img.left-outer.left)*scaleX,y:(img.top-outer.top)*scaleY,
        width:img.width*scaleX,height:img.height*scaleY};
    };
    const boundedCrop=(x,y,width,height)=>{
      const bounds=imageBounds();if(!bounds)return {x,y,width,height};
      const right=bounds.x+bounds.width,bottom=bounds.y+bounds.height;
      const minSize=Math.min(1,bounds.width,bounds.height);
      // Moving preserves current size. Resizing cannot go past an edge.
      const moving=cropperImage.closest('cropper-canvas')?.$action==='move';
      if(moving){
        width=Math.min(width,bounds.width);height=Math.min(height,bounds.height);
        x=Math.max(bounds.x,Math.min(right-width,x));
        y=Math.max(bounds.y,Math.min(bottom-height,y));
      }else{
        if(x<bounds.x){width-=bounds.x-x;x=bounds.x;}
        if(y<bounds.y){height-=bounds.y-y;y=bounds.y;}
        x=Math.max(bounds.x,Math.min(right-minSize,x));
        y=Math.max(bounds.y,Math.min(bottom-minSize,y));
        width=Math.max(minSize,Math.min(width,right-x));
        height=Math.max(minSize,Math.min(height,bottom-y));
      }
      return {x,y,width,height};
    };
    const clampCrop=()=>{
      if(!selection||done)return;
      const bounded=boundedCrop(selection.x,selection.y,selection.width,selection.height);
      if(['x','y','width','height'].some(k=>Math.abs(bounded[k]-selection[k])>.001)){
        selection.$change(bounded.x,bounded.y,bounded.width,bounded.height);
      }
    };
    const onCropChange=event=>{
      const next=event.detail;
      if(!next||!selection)return;
      const bounded=boundedCrop(next.x,next.y,next.width,next.height);
      if(['x','y','width','height'].some(k=>Math.abs(bounded[k]-next[k])>.001)){
        event.preventDefault();
        queueMicrotask(()=>{
          if(!done&&selection)selection.$change(
            bounded.x,bounded.y,bounded.width,bounded.height);
        });
      }else{update();clampLayers();}
    };
    const placeLayer=(layer,left,top,width,height)=>{
      const bounds=selectionBounds();if(!bounds)return;
      width=Math.max(24,Math.min(width,bounds.width));
      height=Math.max(24,Math.min(height,bounds.height));
      left=Math.max(bounds.left,Math.min(left,bounds.left+bounds.width-width));
      top=Math.max(bounds.top,Math.min(top,bounds.top+bounds.height-height));
      Object.assign(layer.el.style,{left:left+'px',top:top+'px',width:width+'px',height:height+'px'});
    };
    const clampLayers=()=>{
      const bounds=selectionBounds();if(!bounds)return;
      for(const layer of pasteLayers) {
        const left=parseFloat(layer.el.style.left)||bounds.left,top=parseFloat(layer.el.style.top)||bounds.top;
        const width=layer.el.offsetWidth||32,height=layer.el.offsetHeight||32;
        placeLayer(layer,left,top,width,height);
      }
    };
    const removeLayer=layer=>{
      const at=pasteLayers.indexOf(layer);if(at>=0)pasteLayers.splice(at,1);
      layer.el.remove();URL.revokeObjectURL(layer.url);
    };
    const addPastedLayer=async file=>{
      if(!selection)throw Error('Crop selection is not ready yet.');
      if(!file||!file.type.startsWith('image/'))throw Error('Clipboard does not contain an image.');
      if(file.size>MAX_BYTES)throw Error('Pasted image exceeds 20 MiB.');
      const objectURL=URL.createObjectURL(file);
      const img=new Image();img.decoding='async';img.src=objectURL;
      try{await img.decode();}catch(e){URL.revokeObjectURL(objectURL);throw Error('Cannot decode pasted image.');}
      const bounds=selectionBounds();if(!bounds){URL.revokeObjectURL(objectURL);throw Error('Crop selection is not ready yet.');}
      const scale=Math.min(bounds.width*.45/img.naturalWidth,bounds.height*.45/img.naturalHeight);
      const width=Math.max(32,img.naturalWidth*scale),height=Math.max(32,img.naturalHeight*scale);
      const el=document.createElement('div');el.className='lantern-crop-paste-layer';el.tabIndex=0;
      el.setAttribute('aria-label','Pasted image layer');
      const resize=document.createElement('button');resize.type='button';resize.className='lantern-crop-paste-resize';resize.setAttribute('aria-label','Resize pasted image');
      const remove=document.createElement('button');remove.type='button';remove.className='lantern-crop-paste-remove';remove.textContent='×';remove.setAttribute('aria-label','Remove pasted image');
      el.append(img,resize,remove);stage.append(el);
      const layer={el,image:img,url:objectURL,ratio:img.naturalWidth/img.naturalHeight};pasteLayers.push(layer);
      placeLayer(layer,bounds.left+(bounds.width-width)/2,bounds.top+(bounds.height-height)/2,width,height);
      el.addEventListener('pointerdown',event=>{
        if(event.button!==0||event.target.closest('button'))return;
        const start={x:event.clientX,y:event.clientY,left:parseFloat(el.style.left)||0,top:parseFloat(el.style.top)||0,width:el.offsetWidth,height:el.offsetHeight};
        el.setPointerCapture(event.pointerId);event.preventDefault();
        const move=e=>placeLayer(layer,start.left+e.clientX-start.x,start.top+e.clientY-start.y,start.width,start.height);
        const end=e=>{el.removeEventListener('pointermove',move);el.releasePointerCapture?.(e.pointerId);};
        el.addEventListener('pointermove',move);el.addEventListener('pointerup',end,{once:true});el.addEventListener('pointercancel',end,{once:true});
      });
      resize.addEventListener('pointerdown',event=>{
        if(event.button!==0)return;
        const start={x:event.clientX,width:el.offsetWidth,left:parseFloat(el.style.left)||0,top:parseFloat(el.style.top)||0};
        resize.setPointerCapture(event.pointerId);event.preventDefault();event.stopPropagation();
        const move=e=>{const width=Math.max(32,start.width+e.clientX-start.x);placeLayer(layer,start.left,start.top,width,width/layer.ratio);};
        const end=e=>{resize.removeEventListener('pointermove',move);resize.releasePointerCapture?.(e.pointerId);};
        resize.addEventListener('pointermove',move);resize.addEventListener('pointerup',end,{once:true});resize.addEventListener('pointercancel',end,{once:true});
      });
      remove.addEventListener('click',event=>{event.preventDefault();event.stopPropagation();removeLayer(layer);});
      status.textContent='Pasted image added. Drag to move; drag the corner to resize.';
    };
    dialog.addEventListener('paste',event=>{
      const item=[...(event.clipboardData?.items||[])].find(x=>x.type?.startsWith('image/'));
      const file=item?.getAsFile?.();
      if(!file)return;
      event.preventDefault();event.stopPropagation();
      void addPastedLayer(file).catch(error=>{status.textContent=error.message||String(error);});
    });
    const update=()=>{
      if(frame||done||!selection||!cropperImage||!source)return;
      frame=requestAnimationFrame(()=>{
        frame=0;
        try {
          const r=selectedPixels(selection,cropperImage,source.naturalWidth,source.naturalHeight);
          measure.textContent=r.width+' × '+r.height+' pixels';
        }catch{measure.textContent='Adjust selection';}
      });
    };
    zoomOut.addEventListener('click',()=>{cropperImage?.$zoom(-.15);update();});
    zoomIn.addEventListener('click',()=>{cropperImage?.$zoom(.15);update();});
    reset.addEventListener('click',()=>{
      cropperImage?.$resetTransform().$center('contain');
      requestAnimationFrame(()=>{
        const bounds=imageBounds();
        if(bounds&&selection)selection.$change(bounds.x,bounds.y,bounds.width,bounds.height);
        clampCrop();update();
      });
    });
    const exportCrop=async action=>{
      if(!selection||!cropperImage||exporting)return;
      exporting=true;for(const control of cropButtons)control.disabled=true;reset.disabled=true;zoomIn.disabled=true;zoomOut.disabled=true;
      status.textContent='Encoding image…';
      try {
        const rect=selectedPixels(selection,cropperImage,source.naturalWidth,source.naturalHeight);
        if(rect.width*rect.height>MAX_PIXELS)throw Error('Crop exceeds the 60 MP export limit; select a smaller area.');
        // Full-frame selection is the default; exporting it is valid, including
        // when the user only adds a pasted layer without trimming the source.
        const canvas=document.createElement('canvas');canvas.width=rect.width;canvas.height=rect.height;
        let blob;
        try {
          const ctx=canvas.getContext('2d');
          if(!ctx)throw Error('No canvas drawing context available.');
          ctx.drawImage(source,rect.x,rect.y,rect.width,rect.height,0,0,rect.width,rect.height);
          if(pasteLayers.length){
            const selectedBox=selection.getBoundingClientRect();
            if(!selectedBox.width||!selectedBox.height)throw Error('Crop selection is not laid out.');
            const scaleX=rect.width/selectedBox.width,scaleY=rect.height/selectedBox.height;
            for(const layer of pasteLayers){
              const box=layer.el.getBoundingClientRect();
              ctx.drawImage(layer.image,(box.left-selectedBox.left)*scaleX,(box.top-selectedBox.top)*scaleY,
                box.width*scaleX,box.height*scaleY);
            }
          }
          const type=format==='image/bmp'||format==='image/webp-alpha'?'image/png':format;
          blob=await toBlob(canvas,type,type==='image/jpeg'?.92:undefined);
          if(blob.type!==type&&!(type==='image/webp'&&blob.type==='image/png'))
            throw Error('Browser did not provide the required encoder.');
          if(blob.size>MAX_BYTES)throw Error('Output exceeds 20 MiB; choose a smaller crop.');
        }finally{canvas.width=0;canvas.height=0;}
        if(!abort.signal.aborted&&!done)finish({blob,extension:imageExtension(blob.type),rect,sourceType:format,action});
      }catch(e){if(!done&&!abort.signal.aborted)status.textContent=e.message||String(e);}
      finally {
        exporting=false;
        if(!done){for(const control of cropButtons)control.disabled=false;reset.disabled=false;zoomIn.disabled=false;zoomOut.disabled=false;}
      }
    };
    apply?.addEventListener('click',()=>{void exportCrop('apply');});
    saveCopy?.addEventListener('click',()=>{void exportCrop('copy');});
    overwrite?.addEventListener('click',()=>{void exportCrop('overwrite');});
    (async()=>{
      try {
        format=await sourceFormat(url.href,abort.signal);
        if(abort.signal.aborted)return;
        const img=new Image();img.decoding='async';img.src=url.href;await img.decode();
        if(abort.signal.aborted)return;
        source=img;
        cropper=new Cropper(img,{container:stage,template:TEMPLATE});
        cropperImage=cropper.getCropperImage();selection=cropper.getCropperSelection();
        if(!cropperImage||!selection)throw Error('Cropper did not create a selection.');
        await cropperImage.$ready();
        if(abort.signal.aborted)return;
        for(const handle of stage.querySelectorAll('cropper-handle[action$="-resize"]')) {
          handle.tabIndex=0;handle.setAttribute('role','button');
          const name={nw:'top left',ne:'top right',sw:'bottom left',se:'bottom right'};
          const corner=handle.getAttribute('action').replace('-resize','');
          handle.setAttribute('aria-label','Resize '+(name[corner]||corner)+' corner');
        }
        selection.tabIndex=0;selection.setAttribute('aria-label','Move crop selection');
        selection.precise=true;
        selection.addEventListener('change',onCropChange);
        cropperImage.addEventListener('transform',()=>{
          requestAnimationFrame(()=>{clampCrop();update();clampLayers();});
        });
        // Cropper may finish its initial layout one frame after image decode.
        // Force full-image selection, rather than 100% of the canvas viewport.
        requestAnimationFrame(()=>{
          const bounds=imageBounds();
          if(bounds && !done)selection.$change(bounds.x,bounds.y,bounds.width,bounds.height);
          update();
        });
        status.textContent='Original image remains unchanged.';
      }catch(e){
        if(!abort.signal.aborted&&!done)status.textContent='Crop unavailable: '+(e.message||String(e));
        for(const control of cropButtons)control.disabled=true;
      }
    })();
  });
}
