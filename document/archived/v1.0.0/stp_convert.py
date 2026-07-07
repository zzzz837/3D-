"""STP→STL converter using pythonocc-core. Called as subprocess by main.py."""
import sys, os, tempfile

def convert_stp_to_stl(input_path):
    from OCC.Core.STEPControl import STEPControl_Reader
    from OCC.Core.StlAPI import StlAPI_Writer
    from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
    from OCC.Core.IFSelect import IFSelect_RetDone

    reader = STEPControl_Reader()
    status = reader.ReadFile(input_path)
    if status != IFSelect_RetDone:
        raise RuntimeError(f"STEP读取失败: {input_path}")

    reader.TransferRoots()
    shape = reader.OneShape()

    # Tessellate for STL export
    mesh = BRepMesh_IncrementalMesh(shape, 1.0, False, 1.0, False)
    mesh.Perform()

    # Write to temp STL file
    fd, stl_path = tempfile.mkstemp(suffix='.stl')
    os.close(fd)
    try:
        writer = StlAPI_Writer()
        writer.Write(shape, stl_path)
        with open(stl_path, 'rb') as f:
            stl_bytes = f.read()
        return stl_bytes
    finally:
        if os.path.exists(stl_path):
            os.remove(stl_path)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(1)
    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    try:
        data = convert_stp_to_stl(input_path)
        if output_path:
            with open(output_path, 'wb') as f:
                f.write(data)
        else:
            sys.stdout.buffer.write(data)
    except Exception as e:
        sys.stderr.write(str(e))
        sys.exit(1)
