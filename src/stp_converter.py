"""
STEP → STL converter using pythonocc-core.
Can be called as:
  - module: convert_step_to_stl(input_path, output_path)
  - script: python stp_converter.py input.stp [output.stl]
"""
import sys, os


def convert_step_to_stl(input_path, output_path=None):
    from OCC.Core.STEPControl import STEPControl_Reader
    from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
    from OCC.Core.StlAPI import StlAPI_Writer

    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"STEP文件不存在: {input_path}")

    reader = STEPControl_Reader()
    status = reader.ReadFile(input_path)
    if status != 1:
        raise RuntimeError(f"无法读取STEP文件 (status={status})")

    reader.TransferRoots()
    shape = reader.OneShape()
    if shape.IsNull():
        raise RuntimeError("STEP 文件无有效几何体")

    mesh = BRepMesh_IncrementalMesh(shape, 1.0, False, 1.0, False)
    mesh.Perform()

    writer = StlAPI_Writer()
    writer.SetASCIIMode(False)

    if output_path:
        writer.Write(shape, output_path)
    else:
        # stdout mode: write to temp file, read back
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".stl", delete=False)
        tmp.close()
        try:
            writer.Write(shape, tmp.name)
            with open(tmp.name, "rb") as f:
                sys.stdout.buffer.write(f.read())
        finally:
            os.unlink(tmp.name)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python stp_converter.py <input.stp> [output.stl]", file=sys.stderr)
        sys.exit(1)
    try:
        convert_step_to_stl(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)
