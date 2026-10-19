"""Independent synthetic vectors and B RTL regression; stdlib only."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import re
import shutil
import signal
import subprocess
import sys
import time
from contextlib import contextmanager

ROOT=Path(__file__).resolve().parents[1]
SOURCES=[ROOT/p for p in (
    'rtl/memory/sram_wrapper.sv','rtl/memory/tensor_buffer.sv',
    'rtl/control/linear_ctrl.sv','rtl/linear_accel_top.sv',
    'tb/models/dot_mac_model.sv','tb/models/tensor_bus_model.sv','tb/tb_linear_accel_top.sv')]
MASK=(1<<40)-1
PROBE_SOURCES=sorted((ROOT/'tb/review_probe').glob('*.sv'))

def source_fingerprints():
    files=SOURCES+PROBE_SOURCES+[Path(__file__).resolve(),ROOT/'Run-B-Tests.ps1']
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}

def case_plan(mode):
    cases=[('tiny',2,64,2,2,0,1),('layers_stalls_faults',3,64,5,12,1,1),
           ('scalar',1,1,1,2,1,1),('odd_dimensions',2,129,3,2,1,1)]
    if mode!='quick':cases.append(('contest_full',99,64,256,12 if mode=='full_layers' else 2,1,0))
    return [{'case':name,'dimensions':[rows,inner,cols],'input_tasks':jobs,
             'stalls':bool(stalls),'fault_tests':bool(faults)}
            for name,rows,inner,cols,jobs,stalls,faults in cases]

COMPONENT_NAMES=['buffer_edges','sram_edges','buffer_reset','high_address',
                 'bad_buffer_width','bad_sram_width','unknown_done','unknown_error']

@contextmanager
def regression_lock(path):
    handle=path.open('a+b')
    handle.seek(0,2)
    if handle.tell()==0:handle.write(b'0');handle.flush()
    handle.seek(0)
    locked=False
    try:
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            locked=True
        except OSError as exc:
            raise RuntimeError('Another B regression is already running in this directory') from exc
        yield
    finally:
        if locked:
            handle.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_UN)
        handle.close()

def resolve_tool(value):
    candidate=Path(value).expanduser()
    if candidate.is_absolute() or candidate.parent!=Path('.') or value.startswith('.'):
        candidate=candidate.resolve()
        if not candidate.is_file():raise FileNotFoundError(f'Tool not found: {candidate}')
        return str(candidate)
    found=shutil.which(value)
    if not found:raise FileNotFoundError(f'Tool not found on PATH: {value}')
    return str(Path(found).resolve())

def write_summary(path,summary):
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    os.replace(temporary,path)

def vectors(folder,rows,inner,cols,jobs):
    xs=[];ws=[];bs=[];ys=[]
    for job in range(jobs):
        rng=random.Random(0x203000+job*701+rows*31+cols)
        x=[[rng.randrange(-127,128) for _ in range(inner)] for _ in range(rows)]
        w=[[rng.randrange(-127,128) for _ in range(cols)] for _ in range(inner)]
        b=[rng.randrange(-(1<<34),1<<34) for _ in range(cols)]
        x[0][0]=-32768; x[-1][-1]=32767; w[0][0]=32767;w[-1][-1]=-32768
        if job%2:
            x[0]=[-32768]*inner
            for k in range(inner):w[k][0]=-32768
            b[0]=(1<<39)-17 # Deliberate modular overflow in TEST arithmetic.
        y=[[(sum(x[i][k]*w[k][j] for k in range(inner))+b[j])&MASK for j in range(cols)] for i in range(rows)]
        xs.extend(value&0xffff for row in x for value in row)
        ws.extend(value&0xffff for row in w for value in row)
        bs.extend(value&MASK for value in b)
        ys.extend(value for row in y for value in row)
    for name,data,digits in [('x',xs,4),('w',ws,4),('b',bs,10),('expected',ys,10)]:
        (folder/f'{name}.hex').write_text(''.join(f'{value:0{digits}x}\n' for value in data),encoding='ascii')
    return ys

def windows_child_handles(process):
    # Tool Help works without taskkill's WMI service. Hold handles for only
    # descendants of our live child, so cleanup never targets a process name.
    # https://learn.microsoft.com/windows/win32/api/tlhelp32/ns-tlhelp32-processentry32w
    import ctypes
    from ctypes import wintypes
    class ProcessEntry(ctypes.Structure):
        _fields_=[('size',wintypes.DWORD),('usage',wintypes.DWORD),('pid',wintypes.DWORD),
                  ('heap',ctypes.c_size_t),('module',wintypes.DWORD),('threads',wintypes.DWORD),
                  ('parent',wintypes.DWORD),('priority',wintypes.LONG),('flags',wintypes.DWORD),
                  ('exe',wintypes.WCHAR*260)]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes=[wintypes.DWORD,wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype=wintypes.HANDLE
    kernel.Process32FirstW.argtypes=[wintypes.HANDLE,ctypes.POINTER(ProcessEntry)]
    kernel.Process32NextW.argtypes=[wintypes.HANDLE,ctypes.POINTER(ProcessEntry)]
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.GetProcessTimes.argtypes=[wintypes.HANDLE]+[ctypes.POINTER(wintypes.FILETIME)]*4
    kernel.TerminateProcess.argtypes=[wintypes.HANDLE,wintypes.UINT]
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    snapshot=kernel.CreateToolhelp32Snapshot(2,0)
    if snapshot==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
    pairs=[]
    try:
        entry=ProcessEntry();entry.size=ctypes.sizeof(entry)
        more=kernel.Process32FirstW(snapshot,ctypes.byref(entry))
        while more:
            pairs.append((int(entry.pid),int(entry.parent)))
            more=kernel.Process32NextW(snapshot,ctypes.byref(entry))
    finally:kernel.CloseHandle(snapshot)
    def born(handle):
        created,exited,kernel_time,user_time=(wintypes.FILETIME() for _ in range(4))
        if not kernel.GetProcessTimes(handle,ctypes.byref(created),ctypes.byref(exited),
                                      ctypes.byref(kernel_time),ctypes.byref(user_time)):
            raise ctypes.WinError(ctypes.get_last_error())
        return (created.dwHighDateTime<<32)|created.dwLowDateTime
    # Windows retains a creator PID after it exits. Creation times prevent a
    # reused parent PID from identifying an unrelated old orphan as our child.
    owned={process.pid:born(int(process._handle))};checked={process.pid};handles=[]
    while True:
        candidates=[(pid,parent) for pid,parent in pairs if parent in owned and pid not in checked]
        if not candidates:break
        for pid,parent in candidates:
            checked.add(pid)
            handle=kernel.OpenProcess(0x00101001,False,pid) # QUERY_LIMITED | SYNCHRONIZE | TERMINATE
            if not handle:continue
            try:
                created=born(handle)
            except OSError:
                kernel.CloseHandle(handle);continue
            if created<owned[parent]:
                kernel.CloseHandle(handle);continue
            owned[pid]=created;handles.append(handle)
    return kernel,handles

def stop_process_tree(process):
    # Only target the PID/group created by execute. Kill descendants before
    # their parent disappears; inherited stdout handles must not prolong waits.
    if os.name=='nt':
        try:
            kernel,handles=windows_child_handles(process)
            try:
                if process.poll() is None:process.kill()
                for handle in handles:kernel.TerminateProcess(handle,1)
                for handle in handles:kernel.WaitForSingleObject(handle,1000)
            finally:
                for handle in handles:kernel.CloseHandle(handle)
        except OSError:
            # Keep the public CLI fallback for hosts where snapshots are denied.
            try:
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],
                               stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL,timeout=5)
            except (OSError,subprocess.TimeoutExpired):pass
    else:
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
    if process.poll() is None:process.kill()
    process.wait(timeout=5)

def execute(command,folder,log_name,timeout,expected_failure=()):
    began=time.monotonic()
    options=({'creationflags':subprocess.CREATE_NEW_PROCESS_GROUP} if os.name=='nt'
             else {'start_new_session':True})
    # Write directly to the current log. Waiting for a pipe to reach EOF can
    # otherwise block after the parent exits if a child inherited that pipe.
    with (folder/log_name).open('wb') as log:
        process=subprocess.Popen(command,cwd=folder,stdout=log,stderr=subprocess.STDOUT,**options)
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            stop_process_tree(process)
            raise RuntimeError(f'{log_name} timed out after {timeout}s')
        except BaseException:
            stop_process_tree(process)
            raise
    output=(folder/log_name).read_text(encoding='utf-8',errors='replace')
    if expected_failure:
        if process.returncode==0 or not any(marker in output for marker in expected_failure):
            raise RuntimeError(f'{log_name}: expected rejection was not observed:\n{output[-3000:]}')
    elif process.returncode:
        raise RuntimeError(f'{log_name} exit {process.returncode}:\n{output[-4000:]}')
    return {'argv':[str(x) for x in command],'returncode':process.returncode,'seconds':round(time.monotonic()-began,3),'output':output}

def check_outputs(folder,expected,rows,cols,expected_runs):
    groups={}
    for line in (folder/'observed.txt').read_text(encoding='ascii').splitlines():
        run,job,index,value=line.split()
        run,job,index,value=int(run),int(job),int(index),int(value,16)
        if run not in expected_runs or job!=expected_runs[run]:raise AssertionError('unexpected run/job identity')
        if not 0<=job<len(expected)//(rows*cols):raise AssertionError('job index out of range')
        if not 0<=index<rows*cols:raise AssertionError(f'output index {index}')
        group=groups.setdefault(run,{'job':job,'seen':set()})
        if job!=group['job'] or index in group['seen']:raise AssertionError('duplicate/mixed output')
        if value!=expected[job*rows*cols+index]:raise AssertionError(f'Python mismatch run={run} index={index}')
        group['seen'].add(index)
    if set(groups)!=set(expected_runs):raise AssertionError('missing or extra successful runs')
    for group in groups.values():
        if len(group['seen'])!=rows*cols:raise AssertionError('missing output')
    return {'complete_jobs':len(groups),'bitwise_checked_outputs':sum(len(g['seen']) for g in groups.values())}

def compile_test(args,folder,top,sources,params=None):
    command=[args.iverilog,'-g2012','-Wall','-s',top,'-o','test.vvp']
    for key,value in (params or {}).items():command+=['-P',f'{top}.{key}={value}']
    command.extend(os.path.relpath(p,folder) for p in sources)
    result=execute(command,folder,'compile.log',60)
    if result['output'].strip():raise RuntimeError(f'Unexpected compiler diagnostics:\n{result["output"]}')
    return result

def run_components(args,root,summary,summary_path):
    specs=[
        ('buffer_edges','tb_tensor_buffer_edges','tb_tensor_buffer_edges.sv','PASS all 9',()),
        ('sram_edges','tb_sram_wrapper_edges','tb_sram_wrapper_edges.sv','PASS all 3',()),
        ('buffer_reset','tb_tensor_buffer_reset_probe','tb_tensor_buffer_reset_probe.sv','PASS writes are blocked',()),
        ('high_address','tb_tensor_buffer_high_addr','tb_tensor_buffer_high_addr.sv','PASS 32-bit high-address',()),
        ('bad_buffer_width','tb_buffer_bad_addr_width','tb_memory_bad_parameters.sv','',('Buffer address width',)),
        ('bad_sram_width','tb_sram_bad_addr_width','tb_memory_bad_parameters.sv','',('SRAM address width',)),
    ]
    for name,top,filename,marker,failure in specs:
        folder=root/('component_'+name);folder.mkdir(exist_ok=True)
        entry={'case':name,'status':'running'};summary['component_tests'].append(entry)
        entry['compile']=compile_test(args,folder,top,SOURCES[:2]+[ROOT/'tb/review_probe'/filename])
        entry['simulation']=execute([args.vvp,'-N','test.vvp'],folder,'simulation.log',30,failure)
        if marker and marker not in entry['simulation']['output']:raise AssertionError(f'{name}: pass marker missing')
        entry['status']='PASS';write_summary(summary_path,summary)
    for name,injection,failure in [('unknown_done',1,('Invalid completion state','UNKNOWN_DUT_CONTROL')),
                                    ('unknown_error',2,('Invalid error state','UNKNOWN_DUT_CONTROL'))]:
        folder=root/('component_'+name);folder.mkdir(exist_ok=True)
        vectors(folder,1,1,1,1)
        entry={'case':name,'status':'running'};summary['component_tests'].append(entry)
        entry['compile']=compile_test(args,folder,'tb_linear_accel_top',SOURCES,
            {'ROWS':1,'INNER':1,'COLS':1,'JOBS':1,'STALLS':1,'TEST_FAULTS':1,'INJECT_UNKNOWN_STATUS':injection})
        entry['simulation']=execute([args.vvp,'-N','test.vvp'],folder,'simulation.log',30,failure)
        entry['status']='PASS';write_summary(summary_path,summary)
    print('PASS component checks: storage edges, reset isolation, bad parameters and X-state rejection',flush=True)

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser()
    modes=parser.add_mutually_exclusive_group()
    modes.add_argument('--quick',action='store_true',help='Skip contest-sized case')
    modes.add_argument('--full-layers',action='store_true',help='Run all 12 synthetic layer tasks at full size')
    def default_tool(name):
        installed=shutil.which(name)
        fallback=Path('D:/Software/iverilog/bin')/(name+'.exe')
        return installed or (str(fallback) if fallback.is_file() else name)
    parser.add_argument('--iverilog',default=default_tool('iverilog'))
    parser.add_argument('--vvp',default=default_tool('vvp'))
    args=parser.parse_args()
    args.iverilog=resolve_tool(args.iverilog);args.vvp=resolve_tool(args.vvp)
    mode='quick' if args.quick else ('full_layers' if args.full_layers else 'standard')
    plan=case_plan(mode)
    root=ROOT/'reports'/'b_regression'
    root.mkdir(parents=True,exist_ok=True)
    summary_path=root/('summary_quick.json' if args.quick else 'summary.json')
    with regression_lock(root/'.run.lock'):
        summary={'schema_version':2,'mode':mode,'case_plan':plan,'component_tests':[],
            'status':'running','scope':'Synthetic B-only RTL tests; no real KWT weights, official SRAM, SoC or synthesis',
            'source_sha256':source_fingerprints(),'cases':[]}
        write_summary(summary_path,summary)
        entry=None
        try:
            run_components(args,root,summary,summary_path)
            for item in plan:
                name=item['case'];rows,inner,cols=item['dimensions'];jobs=item['input_tasks']
                stalls=item['stalls'];faults=item['fault_tests']
                folder=root/name;folder.mkdir(exist_ok=True)
                print(f'Running {name}: {rows}x{inner} * {inner}x{cols}, tasks={jobs}, stalls={int(stalls)}',flush=True)
                entry={**item,'status':'running'};summary['cases'].append(entry)
                expected=vectors(folder,rows,inner,cols,jobs)
                params={'ROWS':rows,'INNER':inner,'COLS':cols,'JOBS':jobs,'STALLS':int(stalls),'TEST_FAULTS':int(faults)}
                entry['compile']=compile_test(args,folder,'tb_linear_accel_top',SOURCES,params)
                entry['simulation']=execute([args.vvp,'-N','test.vvp'],folder,'simulation.log',1800)
                output=entry['simulation']['output']
                if 'B_REGRESSION_PASS' not in output:raise AssertionError('success marker missing')
                records=[tuple(map(int,record)) for record in re.findall(r'^JOB_PASS run=(\d+) job=(\d+) layer=(\d+) cycles=(\d+)\s*$',output,re.M)]
                expected_ids=[(j,j%12) for j in range(jobs)]+([(0,0),(0,0),(0,1)] if faults else [])
                if [(job,layer) for run,job,layer,cycles in records]!=expected_ids:
                    raise AssertionError('wrong successful task/layer coverage')
                runs={run:job for run,job,layer,cycles in records}
                if len(runs)!=len(records):raise AssertionError('duplicate successful run identity')
                entry['comparison']=check_outputs(folder,expected,rows,cols,runs)
                if faults and (output.count('FAULT_PASS')!=8 or 'RESET_RECOVERY_PASS' not in output):
                    raise AssertionError('fault/reset coverage incomplete')
                entry['task_cycles']=[cycles for run,job,layer,cycles in records]
                entry['status']='PASS';write_summary(summary_path,summary)
                print(f"PASS {name}: {entry['comparison']}, simulation={entry['simulation']['seconds']}s",flush=True)
            if source_fingerprints()!=summary['source_sha256']:
                raise RuntimeError('Test sources changed while regression was running; rerun before using results')
        except Exception as exc:
            if entry is not None:entry['status']='FAIL'
            for component in summary['component_tests']:
                if component['status']=='running':
                    component['status']='FAIL';component['error']=str(exc)
            summary['status']='FAIL';summary['error']=str(exc);write_summary(summary_path,summary)
            print(str(exc),flush=True)
            return 1
        summary['status']='PASS';write_summary(summary_path,summary)
    print('B_ALL_TESTS_PASS',flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
