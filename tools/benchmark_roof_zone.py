"""Bounded public-map active-roof zone-retarget timing; no matches or opponents."""
import argparse
import copy
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import time


def summary(rows):
    values=sorted(row['ms'] for row in rows)
    return dict(calls=len(values),p50_ms=round(statistics.median(values),4),
                p99_ms=round(values[max(0,math.ceil(len(values)*.99)-1)],4),
                max_ms=round(max(values),4),over_50ms=sum(t>50 for t in values))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-dir',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output',type=Path)
    args=parser.parse_args();root=args.project_dir.resolve();sys.path.insert(0,str(root))
    from sentinel.altitude import RoofSanctuary
    from sentinel.geometry import World,distance,unit
    with gzip.open(root/'check/stream.jsonl.gz','rt',encoding='utf-8') as stream:
        hello,initial=json.loads(next(stream)),json.loads(next(stream))
    world=World(root/'arena');controller=RoofSanctuary(world,hello['config'])
    all_sites=controller.sites
    distinct={}
    for site in all_sites:
        distinct.setdefault(id(site['prism']),site)
    sites=sorted(distinct.values(),key=lambda s:max(s['prism'].bounds[2]-s['prism'].bounds[0],
                                                  s['prism'].bounds[3]-s['prism'].bounds[1]),reverse=True)[:40]
    if len(sites)<40:
        raise RuntimeError(f'expected40 distinct public roofs, found{len(sites)}')
    evaluations=0
    original=controller.roof_goal_valid
    def counted(*a,**kw):
        nonlocal evaluations
        evaluations+=1
        return original(*a,**kw)
    controller.roof_goal_valid=counted
    rows=[]
    for index,site in enumerate(sites):
        prism=site['prism'];a,b,c,d=prism.bounds;old=site['hold']
        # Preparation is outside timings. A far supported point deliberately
        # makes active same-roof corridor validation longer than a quiet hold.
        candidates=[(a+(c-a)*x,b+(d-b)*y,prism.top)
                    for x in (.1,.3,.5,.7,.9) for y in (.1,.3,.5,.7,.9)]
        candidates=[p for p in candidates if controller.supported(prism,p,2.9) and
                    world.body_clear(*p,2.9,initial['self']['stats']['height'],0)]
        far=max(candidates or [site['landing']],key=lambda p:distance(p,old))
        direction=unit(far[0]-old[0],far[1]-old[1])
        if direction==(0.0,0.0):
            direction=(1.0,0.0)
        for radius in (25,5):
            shift=max(radius+1,distance(far,old))
            near=(old[0]+direction[0]*shift,old[1]+direction[1]*shift)
            off=(c+radius+12,(b+d)/2)
            for name,center in (('near',near),('reject',off)):
                obs=copy.deepcopy(initial)
                obs.update(t=100,tick=2000,events=[],mechs=[],projectiles=[])
                me=obs['self'];me.update(pos=list(old),vel=[0,0,0],grounded=True,
                                        hp=1400,energy=100,in_zone=True)
                obs['zone'].update(center=[0,0],radius=2000,next_center=list(center),
                                   next_radius=radius,shrink_start=101,shrink_end=120)
                controller.site=site;controller.phase='hold';controller.hold_goal=tuple(old)
                controller.deadline=math.inf;controller.reason='timing sample'
                controller.last_hit=-100;controller.next_search=0
                controller.failed={};controller.failed_exits={};controller.valid_cache={}
                controller.exit_goal=None;controller.exit_entry=None;controller.exit_site=None
                controller.exit_progress_position=tuple(old);controller.exit_progress_at=100
                evaluations=0
                start=time.perf_counter_ns()
                action=controller.update(obs,[],(center,radius),allow_start=False)
                elapsed=(time.perf_counter_ns()-start)/1e6
                rows.append(dict(roof=index,case=f'{name}-{radius}',radius=radius,
                                 roof_width=c-a,roof_depth=d-b,forecast_center=center,
                                 old_goal=old,old_goal_outside=not controller.point_in_zone(old,(center,radius)),
                                 ms=elapsed,goal_evaluations=evaluations,phase=controller.phase,
                                 returned_controls=action is not None,
                                 new_goal=controller.hold_goal))
    groups={name:summary([row for row in rows if row['case']==name])
            for name in ('near-25','reject-25','near-5','reject-5')}
    result=dict(kind='active public-roof retarget timing; local host, not match sandbox',
                project=root.name,roof_prisms=len(sites),summary=summary(rows),groups=groups,
                maximum_goal_evaluations=max(r['goal_evaluations'] for r in rows),
                cold_valid_cache_each_sample=True,
                source_sha256=hashlib.sha256((root/'sentinel/altitude.py').read_bytes()).hexdigest(),
                samples=rows)
    if args.output:
        args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='samples'},indent=2))


if __name__=='__main__':
    main()
