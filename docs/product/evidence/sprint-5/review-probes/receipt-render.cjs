// Render the actual domain component offline without changing product code.
const fs = require('node:fs');
const vm = require('node:vm');
const { createRequire } = require('node:module');
const req = createRequire(process.cwd() + '/apps/web/package.json');
const ts = req('typescript');
const react = req('react');
const server = req('react-dom/server');
const source = fs.readFileSync('apps/web/src/domains/hospitality/registration/index.tsx','utf8');
const js = ts.transpileModule(source, {compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
const exported = {};
vm.runInNewContext(js,{exports:exported,require:(name)=> name.startsWith('@/') ? {HospitalityLanding:()=>null} : req(name)});
const brief = {brief_version:2, dates:{check_in:'2027-05-10',check_out:'2027-05-15',nights:5},party:{adults:2,children:[]},pending_fields:[]};
const delta = {dates:{check_out:'2027-05-15',nights:5}};
const rendered = server.renderToStaticMarkup(react.createElement(exported.hospitalityRegistration.guestBriefRenderer,{brief,delta,receipt:{applied_delta:delta}}));
console.log(JSON.stringify({brief,delta,rendered},null,2));
