import sys
import logging
from pathlib import Path
from neuroast.verification.joern_client import joern_session
from neuroast.symbolic.cpg_extractor import CPGExtractor

logging.basicConfig(level=logging.INFO)

def main():
    c_file = Path("benchmarks/datasets/binary_search.c")
    
    # We need to copy the file to .joern_tmp
    joern_tmp_dir = Path(".joern_tmp")
    joern_tmp_dir.mkdir(exist_ok=True)
    target = joern_tmp_dir / "test_raw.c"
    target.write_text(c_file.read_text())
    
    container_path = f"/code/{target}"
    print(f"Container path: {container_path}")
    
    with joern_session(path_on_server=container_path, project_name="test_raw") as joern:
        print("\n--- Methods Query ---")
        methods_raw = joern.query('cpg.method.map(m => (m.name, m.fullName, m.signature, m.lineNumber.getOrElse(-1), m.parameter.name.l, m.methodReturn.typeFullName, m.isExternal)).l')
        print(methods_raw)
        
        print("\n--- Variables Query ---")
        vars_raw = joern.query('cpg.local.map(l => (l.name, l.typeFullName, l.lineNumber.getOrElse(-1), l.code)).l')
        print(vars_raw)
        
        print("\n--- Calls Query ---")
        calls_raw = joern.query('cpg.call.map(c => (c.name, c.methodFullName, c.lineNumber.getOrElse(-1), c.argument.size, c.code)).l')
        print(calls_raw)

if __name__ == "__main__":
    main()
