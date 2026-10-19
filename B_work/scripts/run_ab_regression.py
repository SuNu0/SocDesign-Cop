"""Run B scheduling with A's unchanged compute_lane and external vector files."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

import run_b_regression as common
from a_vectors import load_tasks, crop_task

ROOT=Path(__file__).resolve().parents[1]
B_SOURCES=[ROOT/name for name in (
    'rtl/memory/sram_wrapper.sv','rtl/memory/tensor_buffer.sv',
    'rtl/control/linear_ctrl.sv','rtl/linear_accel_top.sv',
    'rtl/integration/a_compute_adapter.sv','rtl/linear_accel_a_top.sv')]
TB_SOURCES=[ROOT/'tb/models/tensor_bus_model.sv',ROOT/'tb/tb_linear_accel_a_top.sv']
A_NAMES=['rtl/compute/dot64_mac.sv','rtl/compute/bias_requant.sv','rtl/compute/compute_lane.sv']
COMPONENT_NAMES=['adapter_unit','vector_loader_unit']
CASE_ARTIFACTS=('x.hex','w.hex','b.hex','expected.hex','job_layers.hex','job_shifts.hex',
                'input_manifest.json','compile.log','simulation.log','observed.txt',
                'sample_results.csv','test.vvp')
COMPONENT_ARTIFACTS={'adapter_unit':('compile.log','simulation.log','test.vvp'),
                     'vector_loader_unit':('test.log',)}

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def source_fingerprints():
    files=B_SOURCES+TB_SOURCES+[ROOT/name for name in (
        'tb/tb_a_compute_adapter.sv','tb/test_a_vectors.py',
        'scripts/a_vectors.py','scripts/run_ab_regression.py',
        'scripts/run_b_regression.py','Run-AB-Tests.ps1')]
    return {path.relative_to(ROOT).as_posix():digest(path) for path in files}

def a_fingerprints(a_work):return {name:digest(a_work/name) for name in A_NAMES}

def artifact_fingerprints(folder,names):
    result={}
    for name in names:
        path=folder/name
        if not path.is_file():raise FileNotFoundError(f'Expected current-run artifact is missing: {path}')
        result[name]=digest(path)
    return result

def write_run_summary(index_path,run_root,summary):
    # Keep each invocation's evidence, while the familiar summary_<mode>.json
    # names remain the latest index for their mode.
    if run_root.is_dir():common.write_summary(run_root/'summary.json',summary)
    common.write_summary(index_path,summary)

def case_plan(layers,quick=False):
    plan=[{'case':'control_and_recovery','layers':layers,'dimensions':[3,64,5],
           'fault_tests':True,'selection':{'rows':[0,49,98],'cols':[0,1,127,254,255]}}]
    if not quick:
        for start in range(0,len(layers),4):
            group=layers[start:start+4]
            plan.append({'case':'full_'+ '_'.join(f'{layer:02d}' for layer in group),
                         'layers':group,'dimensions':[99,64,256],'fault_tests':False})
    return plan

def locate_a_work(value):
    if value:
        path=Path(value).expanduser().resolve()
    else:
        candidates=[ROOT/'A_work',ROOT.parent/'A_work']
        path=next((item for item in candidates if (item/'rtl/compute/compute_lane.sv').is_file()),candidates[0])
    for name in A_NAMES:
        if not (path/name).is_file():
            raise FileNotFoundError(f'A source missing: {path/name}. Specify --a-work PATH to the shared repository A_work directory.')
    return path

def accepted_diagnostic(line):
    # Keep these compiler messages in the log; reject all other diagnostics.
    return ('bias_requant.sv:' in line and
            ('sorry: constant selects in always_* processes are not fully supported (the process will be sensitive to all bits in ' in line or
             'sorry: constant selects in always_* processes are not currently supported (all bits will be included).' in line))

def compiler_source_path(path,folder):
    try:return os.path.relpath(path,folder)
    except ValueError:return str(path.resolve()) # A and B may live on different Windows drives.

def compile_test(args,folder,top,sources,params=None):
    command=[args.iverilog,'-g2012','-Wall','-s',top,'-o','test.vvp']
    for key,value in (params or {}).items():command+=['-P',f'{top}.{key}={value}']
    command.extend(compiler_source_path(path,folder) for path in sources)
    result=common.execute(command,folder,'compile.log',60)
    lines=[line for line in result['output'].splitlines() if line.strip()]
    unexpected=[line for line in lines if not accepted_diagnostic(line)]
    if unexpected:raise RuntimeError('Unexpected compiler diagnostics:\n'+'\n'.join(unexpected))
    result['accepted_diagnostics']=lines
    return result

def write_case_inputs(folder,tasks):
    for key,filename,bits in [('x','x',16),('w','w',16),('b','b',40),('expected','expected',16)]:
        (folder/f'{filename}.hex').write_text(''.join(f'{value:0{bits//4}x}\n' for task in tasks for value in task[key]),encoding='ascii')
    (folder/'job_layers.hex').write_text(''.join(f"{task['layer']:x}\n" for task in tasks),encoding='ascii')
    (folder/'job_shifts.hex').write_text(''.join(f"{task['shift']:02x}\n" for task in tasks),encoding='ascii')
    (folder/'input_manifest.json').write_text(json.dumps([
        {key:task[key] for key in ('layer','shift','rows','inner','cols','source_sha256')}
        for task in tasks],indent=2),encoding='utf-8')

def signed16(value):return value-65536 if value&32768 else value

def compare_outputs(folder,tasks,runs):
    rows=tasks[0]['rows'];cols=tasks[0]['cols'];seen={run:set() for run in runs}
    samples=[]
    for number,line in enumerate((folder/'observed.txt').read_text(encoding='ascii').splitlines(),1):
        fields=line.split()
        if len(fields)!=4:raise AssertionError(f'Invalid output record at line {number}')
        run,job,index=map(int,fields[:3]);value=int(fields[3],16)
        if run not in runs or job!=runs[run]:raise AssertionError('Wrong output run/job identity')
        if not 0<=job<len(tasks) or not 0<=index<rows*cols:raise AssertionError('Output address out of range')
        if index in seen[run]:raise AssertionError('Duplicate output address')
        expected=tasks[job]['expected'][index]
        row,col=divmod(index,cols)
        if value!=expected:
            mismatch={'layer':tasks[job]['layer'],'run':run,'row':row,'column':col,
                      'expected_hex':f'{expected:04x}','actual_hex':f'{value:04x}',
                      'expected_decimal':signed16(expected),'actual_decimal':signed16(value)}
            (folder/'first_mismatch.json').write_text(json.dumps(mismatch,indent=2),encoding='utf-8')
            raise AssertionError(f'Output mismatch: {mismatch}')
        seen[run].add(index)
        if index<5 or index==rows*cols-1:
            samples.append({'run':run,'layer':tasks[job]['layer'],'row':row,'column':col,
                            'expected_decimal':signed16(expected),'actual_decimal':signed16(value)})
    if any(len(indices)!=rows*cols for indices in seen.values()):raise AssertionError('Missing output values')
    import csv
    with (folder/'sample_results.csv').open('w',encoding='utf-8-sig',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=['run','layer','row','column','expected_decimal','actual_decimal'])
        writer.writeheader();writer.writerows(samples)
    return {'complete_jobs':len(runs),'bitwise_checked_outputs':sum(map(len,seen.values()))}

def run_case(args,a_work,root,item,all_tasks):
    folder=root/item['case']
    entry={**item,'status':'running','input_tasks':len(item['layers']),
           'artifact_directory':item['case']}
    tasks=[]
    simulation_started=False
    print(f"Running {item['case']}: {item['dimensions']}, layers={item['layers']}",flush=True)
    try:
        folder.mkdir()
        tasks=[all_tasks[layer] for layer in item['layers']]
        if item.get('selection'):
            tasks=[crop_task(task,item['selection']['rows'],item['selection']['cols']) for task in tasks]
        write_case_inputs(folder,tasks)
        entry['compile']=compile_test(args,folder,'tb_linear_accel_a_top',
            B_SOURCES+[a_work/name for name in A_NAMES]+TB_SOURCES,
            {'ROWS':tasks[0]['rows'],'COLS':tasks[0]['cols'],'JOBS':len(tasks),
             'STALLS':1,'TEST_FAULTS':int(item['fault_tests'])})
        simulation_started=True
        entry['simulation']=common.execute([args.vvp,'-N','test.vvp'],folder,'simulation.log',2400)
        output=entry['simulation']['output']
        if 'AB_REGRESSION_PASS' not in output:raise AssertionError('AB success marker missing')
        records=[tuple(map(int,record)) for record in re.findall(
            r'^AB_JOB_PASS run=(\d+) job=(\d+) layer=(\d+) shift=(\d+) cycles=(\d+)\s*$',output,re.M)]
        jobs=list(range(len(tasks)))+([0,0,len(tasks)-1] if item['fault_tests'] else [])
        expected=[(job,tasks[job]['layer'],tasks[job]['shift']) for job in jobs]
        if [(job,layer,shift) for run,job,layer,shift,cycles in records]!=expected:
            raise AssertionError('Wrong successful job/layer/shift coverage')
        runs={run:job for run,job,layer,shift,cycles in records}
        if len(runs)!=len(records):raise AssertionError('Duplicate successful run identity')
        if item['fault_tests']:
            faults=re.findall(r'^AB_FAULT_PASS code=(\d+)\s*$',output,re.M)
            if faults!=['1','1','1','1','1','2'] or 'AB_RESET_RECOVERY_PASS' not in output:
                raise AssertionError('Fault/reset coverage incomplete')
        entry['comparison']=compare_outputs(folder,tasks,runs)
        entry['task_cycles']=[cycles for run,job,layer,shift,cycles in records]
        entry['artifact_sha256']=artifact_fingerprints(folder,CASE_ARTIFACTS)
        entry['status']='PASS'
        print(f"PASS {item['case']}: {entry['comparison']}",flush=True)
    except Exception as exc:
        entry['status']='FAIL';entry['error']=str(exc)
        print(f"FAIL {item['case']}: {exc}",flush=True)
        log=folder/'simulation.log'
        if simulation_started and log.is_file():
            match=re.search(r'Output mismatch job=(\d+) index=(\d+) got=([0-9a-fA-F]+) expected=([0-9a-fA-F]+)',log.read_text(encoding='utf-8'))
            if match and 0<=int(match[1])<len(tasks) and 0<=int(match[2])<tasks[0]['rows']*tasks[0]['cols']:
                job,index=int(match[1]),int(match[2]);row,col=divmod(index,tasks[0]['cols'])
                entry['first_mismatch']={'layer':tasks[job]['layer'],'row':row,'column':col,
                    'actual_hex':match[3],'expected_hex':match[4]}
                (folder/'first_mismatch.json').write_text(json.dumps(entry['first_mismatch'],indent=2),encoding='utf-8')
    return entry

def run_components(args,a_work,data_root,layers,root):
    results=[]
    folder=root/'adapter_unit'
    entry={'case':'adapter_unit','status':'running','artifact_directory':'adapter_unit'};results.append(entry)
    try:
        folder.mkdir()
        entry['compile']=compile_test(args,folder,'tb_a_compute_adapter',
            [ROOT/'rtl/integration/a_compute_adapter.sv']+[a_work/name for name in A_NAMES]+[ROOT/'tb/tb_a_compute_adapter.sv'])
        entry['simulation']=common.execute([args.vvp,'-N','test.vvp'],folder,'simulation.log',60)
        if 'A_ADAPTER_UNIT_PASS' not in entry['simulation']['output']:raise AssertionError('Adapter unit marker missing')
        entry['artifact_sha256']=artifact_fingerprints(folder,COMPONENT_ARTIFACTS['adapter_unit'])
        entry['status']='PASS'
        folder=root/'vector_loader_unit'
        entry={'case':'vector_loader_unit','status':'running','artifact_directory':'vector_loader_unit'};results.append(entry)
        folder.mkdir()
        env=os.environ.copy();env['A_VECTORS_TEST_DATA']=str(data_root)
        env['A_VECTORS_TEST_LAYERS']=','.join(map(str,layers))
        command=[sys.executable,'-B',str(ROOT/'tb/test_a_vectors.py'),'-v']
        try:
            process=subprocess.run(command,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                   text=True,encoding='utf-8',errors='replace',timeout=180)
        except subprocess.TimeoutExpired as exc:
            captured=exc.stdout or ''
            if isinstance(captured,bytes):captured=captured.decode('utf-8',errors='replace')
            (folder/'test.log').write_text(captured+'\nVector loader tests timed out after 180 seconds.\n',encoding='utf-8')
            raise RuntimeError('Vector loader tests timed out after 180 seconds; see current run vector_loader_unit/test.log') from exc
        (folder/'test.log').write_text(process.stdout,encoding='utf-8')
        entry['test']={'returncode':process.returncode,'output':process.stdout}
        if process.returncode or not re.search(r'^OK\s*$',process.stdout,re.M):raise AssertionError('External data loader unit tests failed')
        entry['artifact_sha256']=artifact_fingerprints(folder,COMPONENT_ARTIFACTS['vector_loader_unit'])
        entry['status']='PASS'
    except Exception as exc:
        entry['status']='FAIL';entry['error']=str(exc)
        print(f"FAIL {entry['case']}: {exc}",flush=True)
    return results

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--a-work',help='A_work directory containing unchanged A compute RTL')
    parser.add_argument('--data',help='External real_12_layers directory; default A_work/artifacts/real_12_layers')
    modes=parser.add_mutually_exclusive_group()
    modes.add_argument('--layer',type=int,choices=range(12),default=0)
    modes.add_argument('--all-layers',action='store_true')
    parser.add_argument('--quick',action='store_true',help='Crop selected real tasks to 3x64x5, including faults and reset recovery')
    parser.add_argument('--workers',type=int,choices=range(1,5),default=3,help='Independent full-case simulators, default 3')
    parser.add_argument('--iverilog',default=shutil.which('iverilog') or 'D:/Software/iverilog/bin/iverilog.exe')
    parser.add_argument('--vvp',default=shutil.which('vvp') or 'D:/Software/iverilog/bin/vvp.exe')
    args=parser.parse_args()
    layers=list(range(12)) if args.all_layers else [args.layer]
    mode='quick' if args.quick else ('all_layers' if args.all_layers else 'single_layer')
    root=ROOT/'reports/ab_regression';root.mkdir(parents=True,exist_ok=True)
    summary_path=root/f'summary_{mode}.json'
    with common.regression_lock(root/'.run.lock'):
        checked_at=datetime.now(timezone.utc)
        run_name=checked_at.strftime('%Y%m%dT%H%M%S.%fZ')+'_'+uuid.uuid4().hex[:12]+'_'+mode
        run_root=root/'runs'/run_name
        summary={'schema_version':2,'status':'running','checked_at':checked_at.isoformat(),
                 'run_directory':run_root.relative_to(root).as_posix(),
                 'mode':mode,'layers':layers,'case_plan':case_plan(layers,args.quick),
                 'scope':'A production compute RTL + B scheduling/buffers; simulated C memory and behavioral SRAM; no SoC/synthesis',
                 'a_work':None,'data_root':None,'source_sha256':{},
                 'a_source_sha256':{},'input_sha256':{},'component_tests':[],'cases':[]}
        common.write_summary(summary_path,summary)
        try:
            run_root.mkdir(parents=True)
            print(f'A/B run artifacts: {run_root}',flush=True)
            args.iverilog=common.resolve_tool(args.iverilog);args.vvp=common.resolve_tool(args.vvp)
            a_work=locate_a_work(args.a_work)
            data_root=Path(args.data).expanduser().resolve() if args.data else a_work/'artifacts/real_12_layers'
            summary.update(a_work=str(a_work),data_root=str(data_root),source_sha256=source_fingerprints(),
                           a_source_sha256=a_fingerprints(a_work))
            tasks={task['layer']:task for task in load_tasks(data_root,layers)}
            for task in tasks.values():summary['input_sha256'].update(task['source_sha256'])
            summary['component_tests']=run_components(args,a_work,data_root,layers,run_root)
            write_run_summary(summary_path,run_root,summary)
            if any(item['status']!='PASS' for item in summary['component_tests']):raise AssertionError('AB component checks failed')
            # Debug and recovery first; the full cases then use separate simulation
            # processes, each containing up to four consecutive full matrix tasks.
            plan=summary['case_plan']
            entry=run_case(args,a_work,run_root,plan[0],tasks);summary['cases'].append(entry)
            write_run_summary(summary_path,run_root,summary)
            if entry['status']!='PASS':raise AssertionError(entry['error'])
            completed={}
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                pending={pool.submit(run_case,args,a_work,run_root,item,tasks):item['case'] for item in plan[1:]}
                for future in as_completed(pending):
                    item=future.result();completed[item['case']]=item
                    summary['cases']=[entry]+[completed[p['case']] for p in plan[1:] if p['case'] in completed]
                    write_run_summary(summary_path,run_root,summary)
            summary['cases']=[entry]+[completed[item['case']] for item in plan[1:]]
            if any(item['status']!='PASS' for item in summary['cases']):raise AssertionError('A full-size case failed; inspect its simulation.log')
            if source_fingerprints()!=summary['source_sha256'] or a_fingerprints(a_work)!=summary['a_source_sha256']:
                raise AssertionError('RTL or test sources changed during regression; rerun')
            final_inputs={}
            for task in load_tasks(data_root,layers):final_inputs.update(task['source_sha256'])
            if final_inputs!=summary['input_sha256']:
                raise AssertionError('External input changed during regression; rerun')
            summary['status']='PASS'
        except (Exception,KeyboardInterrupt) as exc:
            message='A/B regression interrupted' if isinstance(exc,KeyboardInterrupt) else str(exc)
            summary['status']='FAIL';summary['error']=message
            write_run_summary(summary_path,run_root,summary);print(message,flush=True)
            return 130 if isinstance(exc,KeyboardInterrupt) else 1
        write_run_summary(summary_path,run_root,summary)
    print('AB_ALL_TESTS_PASS',flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
