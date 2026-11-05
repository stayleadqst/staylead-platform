const fs=require('node:fs'),vm=require('node:vm'),{createRequire}=require('node:module');
const req=createRequire(process.cwd()+'/apps/web/package.json'),ts=req('typescript'),react=req('react'),server=req('react-dom/server');
function load(file){const exported={};vm.runInNewContext(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,{exports:exported,require:name=>name.endsWith('/brief-format')?load('apps/web/src/domains/hospitality/registration/brief-format.ts'):name.startsWith('@/')?{HospitalityLanding:()=>null}:req(name)});return exported;}
const component=load('apps/web/src/domains/hospitality/registration/index.tsx').hospitalityRegistration.guestBriefRenderer;
const brief={brief_version:2,dates:{check_in:'2027-05-10',check_out:'2027-05-15',nights:5},party:{adults:2,children:[]},pending_fields:[]},delta={dates:{check_out:'2027-05-15',nights:5}};
const rendered=server.renderToStaticMarkup(react.createElement(component,{brief,delta,receipt:{applied_delta:delta}}));
if(rendered.includes('not set')||!rendered.includes('Check-out changed to 2027-05-15.'))throw new Error(rendered);
const state=load('apps/web/src/shared/chat/chat-state.ts');const retry={};for(const code of ['provider_timeout','freshness_unavailable','storage_unavailable','brief_apply_outcome_unknown']){retry[code]=state.classifyFailure({code,outcome:'rejected',retryable:true}).retryMode;if(retry[code]!=='same-request')throw new Error(code+' unsafe retry');}
for(const code of ['brief_apply_no_effect','request_failed']){retry[code]=state.classifyFailure({code,outcome:'rejected',retryable:true}).retryMode;if(retry[code]!=='new-request')throw new Error(code+' must allow explicit safe retry');}
console.log(JSON.stringify({rendered,retry_modes:retry},null,2));
