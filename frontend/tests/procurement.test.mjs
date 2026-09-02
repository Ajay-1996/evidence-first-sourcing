import test from 'node:test';
import assert from 'node:assert/strict';
import {items,vendors,questions,quote,calculate,source,rawPrice} from '../lib/procurement.ts';
const unresolved={civic:false,fieldstone:false,atlas:false};
const resolved={civic:true,fieldstone:true,atlas:true};
test('five vendors, thirty lines, twelve questions and fifteen sources',()=>{
 assert.equal(vendors.length,5);assert.equal(items.length,30);assert.equal(questions.length,12);assert.equal(vendors.flatMap(v=>v.docs).length,15);
 assert.equal(items.flatMap((_,i)=>vendors.map((__,v)=>rawPrice(i,v))).filter(x=>x!==null).length,147);
});
test('missing and disputed offers cannot win',()=>{
 assert.equal(quote(20,4,unresolved).status,'missing');assert.equal(quote(20,4,unresolved).landed,null);
 assert.equal(quote(29,1,unresolved).landed,null);assert.equal(quote(29,3,unresolved).landed,null);assert.equal(quote(2,4,unresolved).landed,null);
 const r=calculate(unresolved,{quality:false,maxLead:0});
 assert(r.allocations.every(a=>quote(a.line,a.vendor,unresolved).status==='ready'));
});
test('recorded decisions change canonical values but preserve original evidence',()=>{
 assert.equal(quote(29,1,resolved).landed,8750);assert.equal(quote(29,3,resolved).landed,5400);assert.equal(quote(2,4,resolved).landed,630);
 assert.equal(source(2,4,resolved).raw,source(2,4,unresolved).raw);
 assert.notEqual(source(2,4,resolved).formula,source(2,4,unresolved).formula);
});
test('pack normalization charges full purchasable Civic seating packs',()=>{
 assert(Math.abs(quote(7,1,resolved).landed*48-rawPrice(7,1)*50)<.001);
 assert(Math.abs(quote(16,1,resolved).landed*32-rawPrice(16,1)*35)<.001);
 assert.match(source(7,1,resolved).formula,/50 purchased for 48 requested/);
});
test('quality and delivery constrain every award line',()=>{
 const r=calculate(resolved,{quality:true,maxLead:6});assert.equal(r.allocations.length,30);
 assert(r.allocations.every(a=>vendors[a.vendor].score>=80&&vendors[a.vendor].weeks<=6));
 assert.equal(calculate(resolved,{quality:true,maxLead:2}).allocations.length,0);
});
test('allocation totals reconcile and source estimates do not award',()=>{
 const r=calculate(resolved,{quality:true,maxLead:0});
 assert.equal(r.allocations.length,30);
 assert(Math.abs(r.total-r.suppliers.reduce((s,v)=>s+v.total,0))<.001);
 assert(Math.abs(r.total-r.allocations.reduce((s,v)=>s+v.total,0))<.001);
 assert(r.allocations.every(a=>Math.abs(a.total-a.unit*items[a.line].qty)<.011));
});
