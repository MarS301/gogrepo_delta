"""Line coverage of cmd_download over all rig scenarios:  python cover.py path/to/gogrepo_delta.py"""
import ast, os, sys, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rig
path = os.path.abspath(sys.argv[1]); target = os.path.realpath(path)
mod = rig.load_module(path, 'cov_g')
lines = set()
def tracer(frame, event, arg):
    if os.path.realpath(frame.f_code.co_filename) == target:
        if event == 'line': lines.add(frame.f_lineno)
        return tracer
    return None
src = open(path, encoding='utf-8').read(); tree = ast.parse(src); src_lines = src.split('\n')
fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'cmd_download')
stmts = sorted({n.lineno for n in ast.walk(fn) if isinstance(n, ast.stmt) and not isinstance(n, (ast.FunctionDef,)) })
sys.settrace(tracer); threading.settrace(tracer)
for name in rig.SCENARIOS: rig.run(mod, name)
sys.settrace(None); threading.settrace(None)
missed = [l for l in stmts if l not in lines]
print("cmd_download statements: %d, executed by the 32 scenarios: %d (%.0f%%)" % (len(stmts), len(stmts) - len(missed), 100.0 * (len(stmts) - len(missed)) / len(stmts)))
# group the misses
groups = []
for l in missed:
    if groups and l - groups[-1][-1] <= 3: groups[-1].append(l)
    else: groups.append([l])
for g in groups:
    print("  lines %d-%d (%d stmts): %s" % (g[0], g[-1], len(g), src_lines[g[0]-1].strip()[:95]))
