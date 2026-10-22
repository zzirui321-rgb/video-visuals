#!/usr/bin/env node
// Render original, semantic SVG layers as a quiet sequential reveal. No installs or raster retouching.
const fs=require('fs'),path=require('path'),cp=require('child_process'),sharp=require('sharp');
const cfgPath=path.resolve(process.argv[2]||'');
if(!process.argv[2])throw Error('Usage: node render_svg_reveal.cjs animation.json');
const cfg=JSON.parse(fs.readFileSync(cfgPath,'utf8')),base=path.dirname(cfgPath);
const resolve=p=>path.resolve(base,p);
async function main(){
const {width,height,fps=30,duration=7,layers,ffmpeg}=cfg;
if(!Number.isInteger(width)||!Number.isInteger(height)||width<=0||height<=0||width%2||height%2)throw Error('Positive even width/height required');
if(!Number.isInteger(fps)||fps<1||fps>60||!(duration>0)||!ffmpeg||!Array.isArray(layers)||!layers.length)throw Error('Invalid fps/duration/ffmpeg/layers');
const out=resolve(cfg.output);if(fs.existsSync(out))throw Error('Output exists; choose a new versioned output');
const work=resolve(cfg.render_dir||'_render');fs.mkdirSync(work,{recursive:true});fs.mkdirSync(path.dirname(out),{recursive:true});
const all=[{svg:cfg.base_svg,start:0,fade:0},...layers];let args=['-hide_banner','-loglevel','error','-n'];let filters=[];
for(let i=0;i<all.length;i++){
let a=all[i];if(!a.svg||!Number.isFinite(a.start)||!Number.isFinite(a.fade)||a.start<0||a.fade<0||a.start+a.fade>duration-2)throw Error('Every reveal must finish at least 2 seconds before the end');
const svg=fs.readFileSync(resolve(a.svg));if(!svg.toString('utf8').includes('<svg'))throw Error('Only SVG layouts accepted');
let png=path.join(work,`layer_${String(i).padStart(2,'0')}.png`);let img=sharp(svg);const meta=await img.metadata();if(meta.width!==width||meta.height!==height)throw Error('Layer canvas mismatch');
await img.png().toFile(png);args.push('-loop','1','-framerate',String(fps),'-i',png);
if(i===0)filters.push('[0:v]format=rgba[b0]');else {filters.push(`[${i}:v]format=rgba,fade=t=in:st=${a.start}:d=${Math.max(a.fade,1/fps)}:alpha=1[l${i}]`);filters.push(`[b${i-1}][l${i}]overlay=0:0:shortest=1:format=auto[b${i}]`);}
}
args.push('-filter_complex_threads','1','-filter_complex',filters.join(';'),'-map',`[b${all.length-1}]`,'-t',String(duration),'-an','-r',String(fps),'-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',out);
cp.execFileSync(ffmpeg,args,{stdio:'inherit'});console.log(JSON.stringify({output:out,width,height,fps,duration,layers:layers.length}));
}
main().catch(e=>{console.error(e.message);process.exit(1)});
