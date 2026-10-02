#!/usr/bin/env python3
"""Conservatively prove candidate functions have no execution entry.
No coverage verdict is written: emitted ranges must be added to the generator,
where they are checked again before a ledger verdict can close a candidate.
"""
import bisect,csv,hashlib,json,pickle,re,struct
from pathlib import Path
import gen_world_anims as world
tr,gmt=world.tr,world.gmt
img,secs,begins,sha=tr.load_image()
assert sha == world.AUDITED_MAIN_SHA1
cache=Path(__file__).parent/'.disasm_cache/dormant_graph.pkl'
if cache.exists():
    cached=pickle.loads(cache.read_bytes())
else:cached={}
if cached.get('sha')==sha:
    starts,sources,refs=cached['starts'],cached['sources'],cached['refs']
else:
    lo,hi=secs['.text']
    starts,targets,switch,_=tr.global_pass(img,lo,hi)
    sources,leas=gmt.direct_sources(img,lo,hi)
    dec=tr.Decoder(img,starts)
    sources,targets=world.discard_proven_switch_data(dec,sources,targets,switch|leas)
    refs=switch|leas|world.code_refs_outside_unwind(img,secs,lo,hi,starts)
    # Check unaligned data pointers as well, keeping only unwind-code bytes
    # out of the RVA scan. Export address entries are included.
    skip=world.unwind_record_bytes(img,secs)
    for name in ('.rdata','.data'):
        a,b=secs[name]
        for off in range(a,b-3):
            v=struct.unpack_from('<I',img,off)[0]
            if lo<=v<hi and starts[v] and off not in skip:refs.add(v)
            if off+8<=b:
                v=struct.unpack_from('<Q',img,off)[0]-tr.BASE
                if lo<=v<hi and starts[v]:refs.add(v)
    cache.write_bytes(pickle.dumps(dict(sha=sha,starts=starts,sources=sources,refs=refs)))
dec=tr.Decoder(img,starts)
text=(Path.home() / 'tools' / 'main_decompiled.c').read_text(encoding='utf-8',errors='replace')
fstarts=sorted(int(m.group(1),16) for m in re.finditer(r'^// ==== main\+([0-9A-F]{6})  ',text,re.M))
byfn={}
for r in csv.DictReader(open('docs/animation/coverage.csv')):
    if r['status'] in ('to-patch','review','unclassified'):
        byfn.setdefault(int(r['function'],16),[]).append(r['site'])
# Grow the proof across mutually referencing dormant helper functions.
# Seed every possible indirect/data address as reachable; direct edges and
# physical fallthrough then propagate reachability. The resulting union is
# independently checked for ANY entry from outside before it is reported.
nodes={fn:i for i,fn in enumerate(fstarts)}
def owner(a):
    j=bisect.bisect_right(fstarts,a)-1
    return fstarts[j] if j>=0 and a<secs['.text'][1] else None
edges={fn:set() for fn in fstarts}
live={owner(a) for a in refs};live.discard(None)
for target, incoming in sources.items():
    dest=owner(target)
    if dest is None:continue
    for src,_size,_mn in incoming:
        source=owner(src)
        if source is None:live.add(dest)
        elif source!=dest:edges[source].add(dest)
for fn in fstarts:
    pred=gmt.physical_predecessor(dec,starts,fn)
    if pred is not None and pred.mnemonic not in tr.UNCOND|tr.PADDING:
        source=owner(pred.address)
        if source is None:live.add(fn)
        elif source!=fn:edges[source].add(fn)
queue=list(live)
while queue:
    for nxt in edges.get(queue.pop(),()):
        if nxt not in live:live.add(nxt);queue.append(nxt)
# Keep runtime/library funclets outside this gameplay-helper audit.
dead={fn for fn in fstarts if fn not in live and fn<0x650000}
# Only retain the backward closure of dead functions with candidate sites.
closure=set(byfn)&dead
queue=list(closure)
reverse={fn:set() for fn in fstarts}
for source,dests in edges.items():
    for dest in dests:reverse[dest].add(source)
while queue:
    for prev in reverse.get(queue.pop(),()):
        if prev not in closure and prev in dead:closure.add(prev);queue.append(prev)
ranges=[]
for fn in sorted(closure):
    end=fstarts[nodes[fn]+1] if nodes[fn]+1<len(fstarts) else secs['.text'][1]
    if ranges and fn==ranges[-1][1]:ranges[-1][1]=end
    else:ranges.append([fn,end])
def inside(a):
    return owner(a) in closure
problems=[]
for lo,hi in ranges:
    if any(lo<=a<hi for a in refs):problems.append(f'{lo:X}: indirect entry')
    for target,incoming in sources.items():
        if lo<=target<hi:
            problems.extend(f'{target:X}: direct entry {src:X}' for src,_size,_mn in incoming if not inside(src))
    pred=gmt.physical_predecessor(dec,starts,lo)
    if pred is not None and pred.mnemonic not in tr.UNCOND|tr.PADDING and not inside(pred.address):
        problems.append(f'{lo:X}: fallthrough {pred.address:X}')
assert not problems,problems
components=dict(ranges=ranges,sites=[site for fn in sorted(closure) for site in byfn.get(fn,[])])
Path('tools/.disasm_cache/dormant_component.json').write_text(json.dumps(components,indent=2))
print(f'PROVEN UNION: {len(closure)} functions, {len(ranges)} ranges, {len(components["sites"])} candidate sites',flush=True)
proven=[]
for fn,sites in sorted(byfn.items()):
    pos=bisect.bisect_right(fstarts,fn)
    if pos>=len(fstarts):continue
    end=fstarts[pos]
    why=world.dead_code_problem(dec,starts,sources,refs,fn,end)
    if why is None:
        proven.append(dict(start=fn,end=end,sites=sites))
        print(f'{fn:06X}..{end:06X}: {len(sites)} candidates; no execution entry',flush=True)
Path('tools/.disasm_cache/dormant_candidates.json').write_text(json.dumps(proven,indent=2))
print(f'{len(proven)} functions; {sum(len(r["sites"]) for r in proven)} candidates',flush=True)
