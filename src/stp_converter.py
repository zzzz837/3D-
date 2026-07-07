"""
STEP → STL converter using pythonocc-core.
Usage: python stp_converter.py input.stp [> output.stl]
Outputs binary STL bytes to stdout.
"""
import sys

def convert_step_to_stl(input_path):
    try:
        from OCC.Core.STEPControl import STEPControl_Reader
        from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
        from OCC.Core.StlAPI import StlAPI_Writer
    except ImportError:
        print("错误: pythonocc-core 未安装。请运行: pip install pythonocc-core", file=sys.stderr)
        sys.exit(1)

    reader = STEPControl_Reader()
    status = reader.ReadFile(input_path)
    if status != 1:
        print(f"错误: 无法读取 STEP 文件 '{input_path}'", file=sys.stderr)
        sys.exit(1)

    reader.TransferRoots()
    shape = reader.OneShape()

    if shape.IsNull():
        print("错误: STEP 文件无有效几何体", file=sys.stderr)
        sys.exit(1)

    mesh = BRepMesh_IncrementalMesh(shape, 1.0, False, 1.0, False)
    mesh.Perform()

    writer = StlAPI_Writer()
    writer.SetASCIIMode(False)
    memory_buf = writer.Write(shape, True)

    if memory_buf:
        sys.stdout.buffer.write(memory_buf)
    else:
        print("错误: STL 导出失败", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python stp_converter.py <input.stp>", file=sys.stderr)
        sys.exit(1)
    convert_step_to_stl(sys.argv[1])
